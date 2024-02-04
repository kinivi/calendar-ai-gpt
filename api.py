# Import necessary libraries
from quart import Quart, request, jsonify, abort
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from notion_client import Client
import datetime
from dotenv import load_dotenv
import os

# Load environment variables from a .env file for better security and configuration management
load_dotenv()

# Initialize Quart app
app = Quart(__name__)

# Initialize Notion client with an authentication token from environment variables
notion = Client(auth=os.getenv("NOTION_TOKEN"))

# Define the Google API scope needed for calendar access
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_calendar_service():
    """Retrieve Google Calendar service object to interact with the API."""
    creds = None
    # Check if access token exists in 'token.json' for reuse
    if os.path.exists("token.json"):
        with open("token.json", "r") as token:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Refresh or obtain new credentials if necessary
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


@app.route("/read_events", methods=["GET"])
async def read_events():
    """API endpoint to read events from a specified Google Calendar."""
    service = get_calendar_service()

    # Retrieve query parameters with defaults
    calendar_id = request.args.get("calendar_id", "primary")
    time_min = request.args.get(
        "time_min", datetime.datetime.utcnow().isoformat() + "Z"
    )
    time_max = request.args.get("time_max", None)

    try:
        # Call the Google Calendar API to list events
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        return jsonify(events)
    except Exception as e:
        abort(500, description=str(e))


@app.route("/create_event", methods=["POST"])
async def create_event():
    """API endpoint to create a new event in a specified Google Calendar."""
    service = get_calendar_service()
    data = await request.get_json()

    # Retrieve event details from request body
    calendar_id = data.get("calendar_id", "primary")
    summary = data.get("summary")
    description = data.get("description")
    start_time = data.get("start_time")  # Expected in RFC3339 format
    end_time = data.get("end_time")  # Expected in RFC3339 format
    attendees = data.get("attendees", [])  # List of attendee email addresses

    # Validate required fields
    if not all([summary, start_time, end_time]):
        abort(400, description="Missing required event fields.")

    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
        "attendees": [{"email": attendee} for attendee in attendees],
    }

    try:
        # Call the Google Calendar API to create the event
        created_event = (
            service.events().insert(calendarId=calendar_id, body=event).execute()
        )
        return jsonify(created_event)
    except Exception as e:
        abort(500, description=str(e))


@app.route("/delete_event", methods=["DELETE"])
async def delete_event():
    """API endpoint to delete an event from a specified Google Calendar."""
    service = get_calendar_service()

    calendar_id = request.args.get("calendar_id", "primary")
    event_id = request.args.get("event_id")

    if not event_id:
        abort(400, description="Event ID is required.")

    try:
        # Call the Google Calendar API to delete the event
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return jsonify({"status": "success", "message": "Event deleted successfully"})
    except Exception as e:
        abort(500, description=str(e))


@app.route("/list_notion_databases", methods=["GET"])
async def list_notion_databases():
    try:
        response = notion.search(filter={"property": "object", "value": "database"})
        databases = response.get("results", [])
        databases_info = [
            {
                "id": db["id"],
                "title": db["title"][0]["plain_text"]
                if db["title"]
                else "Unnamed Database",
            }
            for db in databases
        ]
        return jsonify(databases_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/list_notion_pages", methods=["GET"])
async def list_notion_pages():
    try:
        response = notion.search(filter={"property": "object", "value": "page"})
        pages = response.get("results", [])
        page_list = []
        for page in pages:
            try:
                title = (
                    page["properties"]["title"]["title"][0]["plain_text"]
                    if page["properties"]["title"]["title"]
                    else "Unnamed Page"
                )
            except:
                title = "Unnamed Page"
            page_info = {
                "id": page["id"],
                "title": title,
                "created_time": page.get("created_time"),
                "last_edited_time": page.get("last_edited_time"),
                "url": page.get("url"),
            }
            page_list.append(page_info)
        return jsonify(page_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Function to retrieve all blocks from a Notion page
def retrieve_all_blocks(block_id):
    try:
        collected_blocks = []
        blocks_to_process = [block_id]

        while blocks_to_process:
            current_block_id = blocks_to_process.pop()
            block_children = notion.blocks.children.list(block_id=current_block_id).get(
                "results", []
            )

            for block in block_children:
                collected_blocks.append(block)
                if block.get("has_children", False):
                    blocks_to_process.append(block["id"])

        return collected_blocks
    except Exception as e:
        return str(e)


# Function to extract text content from Notion blocks
def extract_text_from_blocks(blocks):
    text_content = []

    for block in blocks:
        block_type = block.get("type")
        block_data = block.get(block_type, {})

        if block_type in [
            "paragraph",
            "heading_1",
            "heading_2",
            "heading_3",
            "bulleted_list_item",
            "numbered_list_item",
            "to_do",
        ]:
            text_elements = block_data.get("rich_text", [])
            text_pieces = [element.get("plain_text") for element in text_elements]
            if block_type in ["heading_1", "heading_2", "heading_3"]:
                text_content.append("**" + "".join(text_pieces) + "**")
            else:
                text_content.append("".join(text_pieces))

        elif block_type == "child_page":
            page_title = block_data.get("title", "")
            text_content.append(page_title)

    return text_content


# Function to get all text on a Notion page
def get_all_text_on_page(page_id):
    blocks = retrieve_all_blocks(page_id)
    return extract_text_from_blocks(blocks)


# Endpoint to get text from a Notion page
@app.route("/get_text_from_notion_page", methods=["GET"])
async def get_text_from_notion_page():
    page_id = request.args.get("page_id")
    if not page_id:
        return jsonify({"error": "Page ID is required"}), 400

    try:
        all_text = get_all_text_on_page(page_id)
        return jsonify({"page_id": page_id, "content": all_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Function to query a Notion database
def query_database(database_id):
    try:
        response = notion.databases.query(database_id=database_id)
        return response.get("results", [])
    except Exception as e:
        return str(e)


# Endpoint to get pages from a Notion database
@app.route("/get_notion_database_pages", methods=["GET"])
async def get_notion_database_pages():
    database_id = request.args.get("database_id")
    if not database_id:
        return jsonify({"error": "Database ID is required"}), 400

    try:
        pages = query_database(database_id)
        return jsonify(pages)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Function to retrieve a Notion database schema
def get_database_schema(database_id):
    try:
        return notion.databases.retrieve(database_id=database_id)
    except Exception as e:
        return str(e)


# Endpoint to get a Notion database schema
@app.route("/get_notion_database_schema", methods=["GET"])
async def get_notion_database_schema():
    database_id = request.args.get("database_id")
    if not database_id:
        return jsonify({"error": "Database ID is required"}), 400

    try:
        database_schema = get_database_schema(database_id)
        return jsonify(database_schema)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Function to update a database entry (page) in Notion
def update_database_entry(page_id, updated_properties):
    try:
        response = notion.pages.update(page_id=page_id, properties=updated_properties)
        return response
    except Exception as e:
        return str(e)


# Endpoint to update a Notion database entry
@app.route("/update_notion_database_entry", methods=["POST"])
async def update_notion_database_entry():
    data = await request.get_json()
    page_id = data.get("page_id")
    updated_properties = data.get("updated_properties")

    if not page_id or not updated_properties:
        return jsonify({"error": "Page ID and updated properties are required"}), 400

    try:
        result = update_database_entry(page_id, updated_properties)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Delete token.json file to force re-authentication
    if os.path.exists("token.json"):
        os.remove("token.json")

    app.run()
