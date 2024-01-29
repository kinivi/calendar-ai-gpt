from quart import Quart, request, jsonify, abort
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import datetime

app = Quart(__name__)

# Scopes required for Google Calendar access
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Function to create Google Calendar service
def get_calendar_service():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    service = build('calendar', 'v3', credentials=creds)
    return service

@app.route('/read_events', methods=['GET'])
async def read_events():
    service = get_calendar_service()

    calendar_id = request.args.get('calendar_id', 'primary')
    time_min = request.args.get('time_min', datetime.datetime.utcnow().isoformat() + 'Z')
    time_max = request.args.get('time_max', None)

    try:
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        return jsonify(events)
    except Exception as e:
        abort(500, description=str(e))

@app.route('/create_event', methods=['POST'])
async def create_event():
    service = get_calendar_service()
    data = await request.get_json()

    calendar_id = data.get('calendar_id', 'primary')
    summary = data.get('summary')
    description = data.get('description')
    start_time = data.get('start_time')  # In RFC3339 format
    end_time = data.get('end_time')  # In RFC3339 format
    attendees = data.get('attendees', [])  # List of attendee email addresses

    if not all([summary, start_time, end_time]):
        abort(400, description="Missing required event fields.")

    event = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_time},
        'end': {'dateTime': end_time},
        'attendees': [{'email': attendee} for attendee in attendees],
    }

    try:
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        return jsonify(created_event)
    except Exception as e:
        abort(500, description=str(e))

if __name__ == '__main__':
    app.run()
