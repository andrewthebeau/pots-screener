import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import xml.etree.ElementTree as ET
import io
import base64
from datetime import datetime, timedelta
import numpy as np
import zipfile
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
import plotly.io as pio
import json

app = dash.Dash(__name__, external_stylesheets=[
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css'
], external_scripts=[
    'https://cdn.plot.ly/plotly-2.32.0.min.js'
])
app.title = "POTS Screener"

app_id = globals().get('__app_id', 'default-app-id')
firebase_config = globals().get('__firebase_config', {})
if isinstance(firebase_config, str):
    try:
        firebase_config = json.loads(firebase_config)
    except json.JSONDecodeError:
        print("Warning: __firebase_config is a string but not valid JSON. Using empty dict.")
        firebase_config = {}

app.layout = html.Div(className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-300 font-inter", children=[
    html.Div(className="container mx-auto p-6", children=[
        html.H1("POTS Screener", className="text-4xl font-bold text-center mb-6 text-indigo-700 dark:text-indigo-400"),
        html.Div(className="flex justify-end mb-4", children=[
            html.Button(
                "Toggle Dark Mode",
                id="dark-mode-toggle",
                className="px-4 py-2 bg-gray-300 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg shadow-md hover:bg-gray-400 dark:hover:bg-gray-600 transition-all duration-300"
            )
        ]),
        html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg mb-8", children=[
            html.H2("Upload Apple Health Data", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
            html.P("Please upload the 'export.xml' file from your Apple Health export.zip (found in the 'apple_health_export' folder).", className="mb-4 text-gray-700 dark:text-gray-300"),
            dcc.Upload(
                id='upload-data',
                children=html.Div([
                    'Drag and Drop or ',
                    html.A('Select Files', className="text-indigo-500 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-200")
                ]),
                className="w-full p-6 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-center cursor-pointer hover:border-indigo-500 dark:hover:border-indigo-400 transition-colors duration-200",
                multiple=False
            ),
            html.Div(id='output-data-upload', className="mt-4 text-red-500 dark:text-red-400")
        ]),
        html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg mb-8", children=[
            html.H2("POTS Event Detection Settings", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
            html.Div(className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6", children=[
                html.Div(children=[
                    html.Label("Heart Rate Increase Threshold (bpm)", className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300"),
                    dcc.Slider(
                        id='hr-increase-threshold',
                        min=20, max=50, step=1, value=30,
                        marks={i: str(i) for i in range(20, 51, 5)},
                        tooltip={"placement": "bottom", "always_visible": True},
                        className="mt-2"
                    ),
                ]),
                html.Div(children=[
                    html.Label("Rest Period Duration (minutes)", className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300"),
                    dcc.Slider(
                        id='rest-period-duration',
                        min=3, max=10, step=1, value=5,
                        marks={i: str(i) for i in range(3, 11, 1)},
                        tooltip={"placement": "bottom", "always_visible": True},
                        className="mt-2"
                    ),
                ]),
                html.Div(children=[
                    html.Label("Heart Rate Variation Threshold for Rest (bpm)", className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300"),
                    dcc.Slider(
                        id='variation-threshold',
                        min=3, max=10, step=1, value=5,
                        marks={i: str(i) for i in range(3, 11, 1)},
                        tooltip={"placement": "bottom", "always_visible": True},
                        className="mt-2"
                    ),
                ]),
                html.Div(children=[
                    html.Label("Sustained Increase Duration (seconds)", className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300"),
                    dcc.Slider(
                        id='sustained-duration',
                        min=30, max=120, step=10, value=60,
                        marks={i: str(i) for i in range(30, 121, 30)},
                        tooltip={"placement": "bottom", "always_visible": True},
                        className="mt-2"
                    ),
                ]),
            ]),
            html.Div(id='current-settings', className="mt-4 text-sm text-gray-600 dark:text-gray-400")
        ]),
        html.Div(id='analysis-output', className="hidden", children=[
            html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg mb-8", children=[
                html.H2("POTS Event Summary", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
                html.Div(className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6", children=[
                    html.Div(children=[
                        html.H3("Events Per Day", className="text-xl font-medium mb-2 text-gray-700 dark:text-gray-300"),
                        dash_table.DataTable(
                            id='summary-table',
                            columns=[
                                {"name": "Date", "id": "Date", "type": "datetime"},
                                {"name": "Number of Events", "id": "Number of Events", "type": "numeric"}
                            ],
                            data=[],
                            sort_action="native",
                            row_selectable="single",
                            style_table={'overflowX': 'auto', 'borderRadius': '0.5rem', 'border': '1px solid #e2e8f0'},
                            style_header={
                                'backgroundColor': 'rgb(230, 230, 230)',
                                'fontWeight': 'bold',
                                'color': 'rgb(55, 65, 81)',
                                'borderBottom': '1px solid #cbd5e1',
                                'padding': '0.75rem',
                                'textAlign': 'left'
                            },
                            style_data={
                                'backgroundColor': 'white',
                                'color': 'rgb(55, 65, 81)',
                                'borderBottom': '1px solid #e2e8f0',
                                'padding': '0.75rem',
                                'textAlign': 'left'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': 'rgb(248, 248, 248)'
                                }
                            ],
                            style_cell={
                                'fontFamily': 'Inter',
                                'fontSize': '14px',
                                'whiteSpace': 'normal',
                                'height': 'auto',
                            },
                            export_format='csv',
                            export_headers='display'
                        ),
                        html.Button("Download Summary as CSV", id="btn-download-csv", className="mt-4 px-4 py-2 bg-indigo-500 text-white rounded-lg shadow-md hover:bg-indigo-600 transition-colors duration-200"),
                        dcc.Download(id="download-csv")
                    ]),
                    html.Div(children=[
                        html.H3("Daily Events Chart", className="text-xl font-medium mb-2 text-gray-700 dark:text-gray-300"),
                        dcc.Graph(id='daily-events-chart', config={'displayModeBar': False}, className="rounded-lg shadow-md")
                    ])
                ]),
            ]),
            html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg mb-8", children=[
                html.H2("Heart Rate Over Time", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
                dcc.Graph(id='main-hr-graph', config={'displayModeBar': True}, className="rounded-lg shadow-md"),
                html.Button("Capture Main Graph Screenshot", id="btn-screenshot-main", className="mt-4 px-4 py-2 bg-teal-500 text-white rounded-lg shadow-md hover:bg-teal-600 transition-colors duration-200"),
                dcc.Download(id="download-main-screenshot")
            ]),
            html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg mb-8", children=[
                html.H2("Zoomed-In POTS Events", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
                html.Div(id='zoomed-in-graphs', className="grid grid-cols-1 md:grid-cols-2 gap-6"),
                html.Button("Export All Graphs as PDF", id="btn-export-pdf", className="mt-6 mr-4 px-4 py-2 bg-green-500 text-white rounded-lg shadow-md hover:bg-green-600 transition-colors duration-200"),
                dcc.Download(id="download-pdf"),
                html.Button("Export All Graphs as Zip File", id="btn-export-zip", className="mt-6 px-4 py-2 bg-blue-500 text-white rounded-lg shadow-md hover:bg-blue-600 transition-colors duration-200"),
                dcc.Download(id="download-zip")
            ])
        ]),
        html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg mb-8", children=[
            html.H2("Understanding POTS", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
            dcc.Markdown(
                """
                Postural Orthostatic Tachycardia Syndrome (POTS) is a condition of the autonomic nervous system,
                which controls involuntary bodily functions like heart rate, blood pressure, and digestion.

                **Key Characteristics:**
                * A sustained increase in heart rate of $\ge$30 beats per minute (bpm) (or $\ge$40 bpm in adolescents)
                    within 10 minutes of standing or head-up tilt.
                * This increase occurs without a significant drop in blood pressure (orthostatic hypotension).
                * Symptoms are typically relieved by lying down.

                **Common Symptoms:**
                * Dizziness or lightheadedness
                * Fainting or near-fainting
                * Fatigue
                * Brain fog
                * Palpitations
                * Shortness of breath
                * Chest pain
                * Nausea
                * Tremors

                **Diagnosis:**
                Diagnosis of POTS typically involves a Tilt Table Test or an Active Stand Test performed by a medical professional.
                These tests help confirm the heart rate increase upon standing and rule out other conditions.

                **Important Disclaimer:**
                This app is a screening tool to identify potential POTS events based on heart rate data.
                **It is not a substitute for professional medical diagnosis.**
                Consult a healthcare provider for accurate diagnosis, treatment, and management of POTS or any other medical condition.
                """,
                className="prose dark:prose-invert max-w-none text-gray-700 dark:text-gray-300"
            )
        ]),
        html.Div(className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg", children=[
            html.H2("Help & Instructions", className="text-2xl font-semibold mb-4 text-indigo-600 dark:text-indigo-300"),
            dcc.Markdown(
                """
                **How to Export Data from Apple Health:**
                1.  Open the Health app on your iPhone.
                2.  Tap your profile picture in the top right corner.
                3.  Scroll down and tap "Export All Health Data".
                4.  Confirm the export. This will create a `health_export.zip` file.
                5.  Transfer this zip file to your computer.
                6.  Unzip the file. Inside, you'll find a folder named `apple_health_export`.
                7.  Locate the `export.xml` file within the `apple_health_export` folder. This is the file you need to upload.

                **Using the POTS Screener App:**
                1.  **Upload XML File:** Click "Select Files" or drag and drop your `export.xml` file into the designated area.
                2.  **Adjust Settings:** Use the sliders in the "POTS Event Detection Settings" panel to customize the criteria for identifying potential POTS events. Your current settings will be displayed below the sliders.
                3.  **Review Summary:** Once the data is processed, a summary table will show the number of potential POTS events per day. You can sort this table and download it as a CSV.
                4.  **Explore Graphs:**
                    * The "Heart Rate Over Time" graph displays your heart rate data with detected POTS events highlighted.
                    * The "Daily Events Chart" provides a quick visualization of event frequency.
                    * Clicking a row in the "Events Per Day" table will filter the main graph to that specific day and generate detailed "Zoomed-In POTS Events" graphs for each event on that day.
                5.  **Export Results:** Use the buttons to export the summary table, capture screenshots of individual graphs, or generate a PDF/Zip file containing all graphs.
                """,
                className="prose dark:prose-invert max-w-none text-gray-700 dark:text-gray-300"
            )
        ])
    ]),
    dcc.Store(id='stored-data', data=None),
    dcc.Store(id='pots-events-data', data=None),
    dcc.Store(id='current-day-data', data=None),
    dcc.Store(id='settings-store', storage_type='local'),
    html.Div(id='hidden-div', style={'display': 'none'})
])

app.clientside_callback(
    """
    function toggleDarkMode(n_clicks) {
        if (n_clicks) {
            document.documentElement.classList.toggle('dark');
            let isDarkMode = document.documentElement.classList.contains('dark');
            localStorage.setItem('darkMode', isDarkMode);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('hidden-div', 'children'),
    Input('dark-mode-toggle', 'n_clicks'),
    prevent_initial_call=True
)

app.clientside_callback(
    """
    function applyDarkModeOnLoad() {
        if (localStorage.getItem('darkMode') === 'true') {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('hidden-div', 'children'),
    Input('dark-mode-toggle', 'id')
)

@app.callback(
    Output('current-settings', 'children'),
    Output('settings-store', 'data'),
    Input('hr-increase-threshold', 'value'),
    Input('rest-period-duration', 'value'),
    Input('variation-threshold', 'value'),
    Input('sustained-duration', 'value')
)
def update_settings_display(hr_threshold, rest_duration, var_threshold, sustained_duration):
    settings = {
        'hr_increase_threshold': hr_threshold,
        'rest_period_duration': rest_duration,
        'variation_threshold': var_threshold,
        'sustained_duration': sustained_duration
    }
    display_text = f"Current Settings: HR Increase: {hr_threshold} bpm, Rest Period: {rest_duration} min, Variation: {var_threshold} bpm, Sustained: {sustained_duration} sec."
    return display_text, settings

@app.callback(
    Output('hr-increase-threshold', 'value'),
    Output('rest-period-duration', 'value'),
    Output('variation-threshold', 'value'),
    Output('sustained-duration', 'value'),
    Input('settings-store', 'data')
)
def load_settings_from_store(settings_data):
    if settings_data:
        return (
            settings_data.get('hr_increase_threshold', 30),
            settings_data.get('rest_period_duration', 5),
            settings_data.get('variation_threshold', 5),
            settings_data.get('sustained_duration', 60)
        )
    return 30, 5, 5, 60

@app.callback(
    Output('output-data-upload', 'children'),
    Output('stored-data', 'data'),
    Output('analysis-output', 'className'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    State('upload-data', 'last_modified')
)
def upload_and_parse_xml(contents, filename, last_modified):
    if contents is not None:
        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            if filename != 'export.xml':
                return html.Div('Error: Please upload the export.xml file from the apple_health_export folder.', className="text-red-500"), None, "hidden"
            heart_rate_data = []
            context = ET.iterparse(io.BytesIO(decoded), events=('end',))
            for event, elem in context:
                if event == 'end' and elem.tag == 'Record' and elem.get('type') == 'HKQuantityTypeIdentifierHeartRate':
                    try:
                        start_date_str = elem.get('startDate')
                        value_str = elem.get('value')
                        if start_date_str and value_str:
                            try:
                                timestamp = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M:%S %z')
                            except ValueError:
                                timestamp = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M:%S')
                            heart_rate = float(value_str)
                            heart_rate_data.append({'timestamp': timestamp, 'heart_rate': heart_rate})
                    except (ValueError, TypeError) as e:
                        print(f"Skipping record due to parsing error: {e}, Data: {elem.attrib}")
                    elem.clear()
            if not heart_rate_data:
                return html.Div('No heart rate data found in the XML file. Please ensure it contains "HKQuantityTypeIdentifierHeartRate" records.', className="text-red-500"), None, "hidden"
            df = pd.DataFrame(heart_rate_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            return html.Div(f'Successfully uploaded {filename}. Processing data...', className="text-green-500"), df.to_json(date_format='iso', orient='split'), ""
        except Exception as e:
            print(f"Error processing file: {e}")
            return html.Div(f'There was an error processing your file: {e}', className="text-red-500"), None, "hidden"
    return html.Div(''), None, "hidden"

def detect_pots_events(df, hr_increase_threshold, rest_period_duration, variation_threshold, sustained_duration_sec):
    if df.empty:
        return []
    pots_events = []
    df = df.sort_values('timestamp').reset_index(drop=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    sustained_duration_td = timedelta(seconds=sustained_duration_sec)
    rest_period_td = timedelta(minutes=rest_period_duration)
    check_next_td = timedelta(minutes=10)
    i = 0
    while i < len(df):
        rest_start_idx = i
        rest_end_time = df['timestamp'].iloc[rest_start_idx] + rest_period_td
        rest_period_readings = df[(df['timestamp'] >= df['timestamp'].iloc[rest_start_idx]) & (df['timestamp'] < rest_end_time)]
        if len(rest_period_readings) >= 5 and rest_period_readings['heart_rate'].std() < variation_threshold:
            baseline_hr = rest_period_readings['heart_rate'].mean()
            rest_start_time = df['timestamp'].iloc[rest_start_idx]
            rest_end_idx = rest_period_readings.index[-1]
            check_start_time = rest_end_time
            check_end_time = check_start_time + check_next_td
            post_rest_readings = df[(df['timestamp'] >= check_start_time) & (df['timestamp'] < check_end_time)]
            if not post_rest_readings.empty:
                potential_increase_readings = post_rest_readings[post_rest_readings['heart_rate'] >= (baseline_hr + hr_increase_threshold)]
                if not potential_increase_readings.empty:
                    increase_time = potential_increase_readings['timestamp'].min()
                    increase_hr = potential_increase_readings[potential_increase_readings['timestamp'] == increase_time]['heart_rate'].iloc[0]
                    sustained_check_start_time = increase_time
                    sustained_check_end_time = increase_time + sustained_duration_td
                    sustained_readings = df[(df['timestamp'] >= sustained_check_start_time) & (df['timestamp'] < sustained_check_end_time)]
                    if not sustained_readings.empty and (sustained_readings['heart_rate'] >= (baseline_hr + hr_increase_threshold)).all():
                        pots_events.append({
                            'start_time': rest_start_time,
                            'increase_time': increase_time,
                            'end_time': sustained_check_end_time,
                            'baseline_hr': baseline_hr,
                            'peak_hr': increase_hr,
                            'duration_to_peak': (increase_time - rest_start_time).total_seconds(),
                            'sustained_duration': sustained_duration_td.total_seconds()
                        })
                        i = df[df['timestamp'] >= sustained_check_end_time].index.min() if not df[df['timestamp'] >= sustained_check_end_time].empty else len(df)
                        continue
        i += 1
    return pots_events

@app.callback(
    Output('pots-events-data', 'data'),
    Output('summary-table', 'data'),
    Output('daily-events-chart', 'figure'),
    Output('main-hr-graph', 'figure'),
    Input('stored-data', 'data'),
    Input('hr-increase-threshold', 'value'),
    Input('rest-period-duration', 'value'),
    Input('variation-threshold', 'value'),
    Input('sustained-duration', 'value')
)
def update_analysis_outputs(jsonified_cleaned_data, hr_threshold, rest_duration, var_threshold, sustained_duration):
    if jsonified_cleaned_data is None:
        empty_fig = go.Figure()
        empty_fig.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        return None, [], empty_fig, empty_fig
    try:
        df = pd.read_json(jsonified_cleaned_data, orient='split')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except ValueError as e:
        print(f"Error decoding stored data: {e}")
        empty_fig = go.Figure()
        empty_fig.update_layout(template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        return None, [], empty_fig, empty_fig
    pots_events = detect_pots_events(df, hr_threshold, rest_duration, var_threshold, sustained_duration)
    serializable_pots_events = []
    for event in pots_events:
        serializable_pots_events.append({
            k: v.isoformat() if isinstance(v, datetime) else v
            for k, v in event.items()
        })
    if pots_events:
        events_df = pd.DataFrame(pots_events)
        events_df['date'] = events_df['start_time'].dt.date
        daily_events = events_df.groupby('date').size().reset_index(name='Number of Events')
        daily_events['Date'] = daily_events['date'].astype(str)
        summary_table_data = daily_events.to_dict('records')
    else:
        summary_table_data = []
    daily_chart_fig = go.Figure()
    if daily_events:
        daily_chart_fig.add_trace(go.Bar(
            x=daily_events['Date'],
            y=daily_events['Number of Events'],
            marker_color='indigo'
        ))
        daily_chart_fig.update_layout(
            title_text='Daily Potential POTS Events',
            xaxis_title='Date',
            yaxis_title='Number of Events',
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter", color="gray"),
            title_font_color="indigo"
        )
    else:
        daily_chart_fig.update_layout(
            annotations=[dict(text="No POTS events detected for daily chart.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color="gray"))],
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
    main_hr_fig = go.Figure()
    if not df.empty:
        main_hr_fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['heart_rate'],
            mode='lines',
            name='Heart Rate (bpm)',
            line=dict(color='rgb(79, 70, 229)', shape='spline')
        ))
        shapes = []
        annotations = []
        for event in pots_events:
            shapes.append(
                dict(
                    type="rect",
                    xref="x", yref="paper",
                    x0=event['start_time'], y0=0,
                    x1=event['end_time'], y1=1,
                    fillcolor="rgba(255,0,0,0.2)",
                    line_width=0,
                    layer="below"
                )
            )
            annotations.append(
                dict(
                    x=event['increase_time'], y=event['peak_hr'],
                    xref="x", yref="y",
                    text=f"POTS Event<br>Peak: {int(event['peak_hr'])} bpm",
                    showarrow=True,
                    arrowhead=2,
                    ax=0, ay=-40,
                    bgcolor="rgba(255,255,255,0.7)",
                    bordercolor="rgba(255,0,0,0.7)",
                    borderwidth=1,
                    borderpad=4,
                    font=dict(size=10, color="red")
                )
            )
        main_hr_fig.update_layout(
            shapes=shapes,
            annotations=annotations,
            title_text='Heart Rate Over Time with Potential POTS Events',
            xaxis_title='Timestamp',
            yaxis_title='Heart Rate (bpm)',
            hovermode='x unified',
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter", color="gray"),
            title_font_color="indigo",
            xaxis=dict(rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=6, label="6h", step="hour", stepmode="backward"),
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all")
                ])
            ), rangeslider=dict(visible=True), type="date")
        )
    else:
        main_hr_fig.update_layout(
            annotations=[dict(text="Upload data to see heart rate graph.", xref="paper", yref="paper", showarrow=False, font=dict(size=16, color="gray"))],
            template="plotly_white",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
    return serializable_pots_events, summary_table_data, daily_chart_fig, main_hr_fig

@app.callback(
    Output('main-hr-graph', 'figure', allow_duplicate=True),
    Output('zoomed-in-graphs', 'children'),
    Output('current-day-data', 'data'),
    Input('summary-table', 'selected_rows'),
    State('summary-table', 'data'),
    State('stored-data', 'data'),
    State('pots-events-data', 'data'),
    prevent_initial_call=True
)
def update_graphs_on_row_select(selected_rows, summary_data, jsonified_cleaned_data, serializable_pots_events):
    if not selected_rows or not jsonified_cleaned_data or not serializable_pots_events:
        return dash.no_update, html.Div("Select a day in the summary table to view detailed event graphs."), None
    selected_row_index = selected_rows[0]
    selected_date_str = summary_data[selected_row_index]['Date']
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    df = pd.read_json(jsonified_cleaned_data, orient='split')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df_day = df[df['timestamp'].dt.date == selected_date]
    pots_events_day = [
        {k: datetime.fromisoformat(v) if isinstance(v, str) and 'T' in v else v for k, v in event.items()}
        for event in serializable_pots_events
        if datetime.fromisoformat(event['start_time']).date() == selected_date
    ]
    main_hr_fig = go.Figure()
    main_hr_fig.add_trace(go.Scatter(
        x=df_day['timestamp'],
        y=df_day['heart_rate'],
        mode='lines',
        name='Heart Rate (bpm)',
        line=dict(color='rgb(79, 70, 229)', shape='spline')
    ))
    shapes = []
    annotations = []
    for event in pots_events_day:
        shapes.append(
            dict(
                type="rect",
                xref="x", yref="paper",
                x0=event['start_time'], y0=0,
                x1=event['end_time'], y1=1,
                fillcolor="rgba(255,0,0,0.2)",
                line_width=0,
                layer="below"
            )
        )
        annotations.append(
            dict(
                x=event['increase_time'], y=event['peak_hr'],
                xref="x", yref="y",
                text=f"POTS Event<br>Peak: {int(event['peak_hr'])} bpm",
                showarrow=True,
                arrowhead=2,
                ax=0, ay=-40,
                bgcolor="rgba(255,255,255,0.7)",
                bordercolor="rgba(255,0,0,0.7)",
                borderwidth=1,
                borderpad=4,
                font=dict(size=10, color="red")
            )
        )
    main_hr_fig.update_layout(
        shapes=shapes,
        annotations=annotations,
        title_text=f'Heart Rate for {selected_date_str} with Potential POTS Events',
        xaxis_title='Timestamp',
        yaxis_title='Heart Rate (bpm)',
        hovermode='x unified',
        template="plotly_white",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color="gray"),
        title_font_color="indigo",
        xaxis=dict(
            range=[df_day['timestamp'].min(), df_day['timestamp'].max()],
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=6, label="6h", step="hour", stepmode="backward"),
                    dict(count=1, label="1d", step="day", stepmode="backward"),
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all")
                ])
            ), rangeslider=dict(visible=True), type="date"
        )
    )
    zoomed_in_graphs = []
    for i, event in enumerate(pots_events_day):
        graph_start_time = event['start_time'] - timedelta(minutes=5)
        graph_end_time = event['increase_time'] + timedelta(minutes=10)
        df_event_window = df[(df['timestamp'] >= graph_start_time) & (df['timestamp'] <= graph_end_time)]
        if not df_event_window.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_event_window['timestamp'],
                y=df_event_window['heart_rate'],
                mode='lines',
                name='Heart Rate (bpm)',
                line=dict(color='rgb(79, 70, 229)', shape='spline')
            ))
            fig.add_shape(
                type="rect",
                xref="x", yref="paper",
                x0=event['start_time'], y0=0,
                x1=event['end_time'], y1=1,
                fillcolor="rgba(255,0,0,0.2)",
                line_width=0,
                layer="below"
            )
            fig.add_annotation(
                x=event['increase_time'], y=event['peak_hr'],
                xref="x", yref="y",
                text=f"POTS Event<br>Peak: {int(event['peak_hr'])} bpm",
                showarrow=True,
                arrowhead=2,
                ax=0, ay=-40,
                bgcolor="rgba(255,255,255,0.7)",
                bordercolor="rgba(255,0,0,0.7)",
                borderwidth=1,
                borderpad=4,
                font=dict(size=10, color="red")
            )
            fig.update_layout(
                title_text=f'POTS Event {i+1} on {selected_date_str} (Baseline: {int(event["baseline_hr"])} bpm)',
                xaxis_title='Timestamp',
                yaxis_title='Heart Rate (bpm)',
                hovermode='x unified',
                template="plotly_white",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Inter", color="gray"),
                title_font_color="indigo",
                xaxis=dict(
                    range=[graph_start_time, graph_end_time],
                    rangeslider=dict(visible=True),
                    type="date"
                )
            )
            zoomed_in_graphs.append(
                html.Div(dcc.Graph(figure=fig, config={'displayModeBar': True}), className="rounded-lg shadow-md")
            )
    current_day_data_json = df_day.to_json(date_format='iso', orient='split')
    current_day_pots_events_json = [
        {k: v.isoformat() if isinstance(v, datetime) else v for k, v in event.items()}
        for event in pots_events_day
    ]
    return main_hr_fig, zoomed_in_graphs, {'df_day': current_day_data_json, 'pots_events_day': current_day_pots_events_json}

@app.callback(
    Output("download-csv", "data"),
    Input("btn-download-csv", "n_clicks"),
    State("summary-table", "data"),
    prevent_initial_call=True,
)
def download_summary_csv(n_clicks, summary_data):
    if n_clicks:
        df_summary = pd.DataFrame(summary_data)
        return dcc.send_data_frame(df_summary.to_csv, "pots_summary.csv", index=False)

app.clientside_callback(
    """
    function captureScreenshot(n_clicks, graph_id) {
        if (n_clicks) {
            const graphDiv = document.getElementById(graph_id);
            if (graphDiv) {
                Plotly.downloadImage(graphDiv, {format: 'png', filename: graph_id + '_screenshot'});
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('download-main-screenshot', 'data'),
    Input('btn-screenshot-main', 'n_clicks'),
    State('main-hr-graph', 'id'),
    prevent_initial_call=True
)

@app.callback(
    Output("download-pdf", "data"),
    Input("btn-export-pdf", "n_clicks"),
    State('main-hr-graph', 'figure'),
    State('daily-events-chart', 'figure'),
    State('zoomed-in-graphs', 'children'),
    State('summary-table', 'data'),
    State('current-day-data', 'data'),
    prevent_initial_call=True,
)
def export_all_graphs_as_pdf(n_clicks, main_fig_json, daily_chart_fig_json, zoomed_in_graphs_children, summary_table_data, current_day_data_json):
    if n_clicks:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph("POTS Screener Report", styles['h1']))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("POTS Event Summary", styles['h2']))
        if summary_table_data:
            df_summary = pd.DataFrame(summary_table_data)
            table_data = [df_summary.columns.tolist()] + df_summary.values.tolist()
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(table)
        else:
            story.append(Paragraph("No summary data available.", styles['Normal']))
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("Daily Potential POTS Events Chart", styles['h2']))
        if daily_chart_fig_json:
            daily_chart_fig = go.Figure(daily_chart_fig_json)
            daily_chart_img_bytes = pio.to_image(daily_chart_fig, format='png', width=800, height=400)
            img = Image(io.BytesIO(daily_chart_img_bytes), width=7.5*inch, height=3.75*inch)
            story.append(img)
        else:
            story.append(Paragraph("No daily events chart available.", styles['Normal']))
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("Heart Rate Over Time with Potential POTS Events", styles['h2']))
        if main_fig_json:
            main_fig = go.Figure(main_fig_json)
            main_fig_img_bytes = pio.to_image(main_fig, format='png', width=1000, height=500)
            img = Image(io.BytesIO(main_fig_img_bytes), width=9.5*inch, height=4.75*inch)
            story.append(img)
        else:
            story.append(Paragraph("No main heart rate graph available.", styles['Normal']))
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("Zoomed-In POTS Event Details", styles['h2']))
        if zoomed_in_graphs_children:
            for i, child in enumerate(zoomed_in_graphs_children):
                if 'props' in child and 'figure' in child['props']:
                    fig_json = child['props']['figure']
                    fig = go.Figure(fig_json)
                    img_bytes = pio.to_image(fig, format='png', width=800, height=400)
                    img = Image(io.BytesIO(img_bytes), width=7.5*inch, height=3.75*inch)
                    story.append(Paragraph(f"Event {i+1} Graph:", styles['h3']))
                    story.append(img)
                    story.append(Spacer(1, 0.2 * inch))
        else:
            story.append(Paragraph("No zoomed-in event graphs generated. Select a day in the summary table to view them.", styles['Normal']))
        story.append(Spacer(1, 0.5 * inch))
        doc.build(story)
        buffer.seek(0)
        return dcc.send_bytes(buffer.getvalue(), "pots_report.pdf")
    return None

@app.callback(
    Output("download-zip", "data"),
    Input("btn-export-zip", "n_clicks"),
    State('main-hr-graph', 'figure'),
    State('daily-events-chart', 'figure'),
    State('zoomed-in-graphs', 'children'),
    prevent_initial_call=True,
)
def export_all_graphs_as_zip(n_clicks, main_fig_json, daily_chart_fig_json, zoomed_in_graphs_children):
    if n_clicks:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            if main_fig_json:
                main_fig = go.Figure(main_fig_json)
                main_img_bytes = pio.to_image(main_fig, format='png', width=1200, height=600)
                zf.writestr("main_hr_graph.png", main_img_bytes)
            if daily_chart_fig_json:
                daily_chart_fig = go.Figure(daily_chart_fig_json)
                daily_chart_img_bytes = pio.to_image(daily_chart_fig, format='png', width=800, height=400)
                zf.writestr("daily_events_chart.png", daily_chart_img_bytes)
            if zoomed_in_graphs_children:
                for i, child in enumerate(zoomed_in_graphs_children):
                    if 'props' in child and 'figure' in child['props']:
                        fig_json = child['props']['figure']
                        fig = go.Figure(fig_json)
                        img_bytes = pio.to_image(fig, format='png', width=800, height=400)
                        zf.writestr(f"pots_event_{i+1}.png", img_bytes)
        zip_buffer.seek(0)
        return dcc.send_bytes(zip_buffer.getvalue(), "pots_graphs.zip")
    return None

if __name__ == '__main__':
    app.run_server(debug=True)
