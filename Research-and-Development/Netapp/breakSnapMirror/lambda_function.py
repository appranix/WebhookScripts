import requests
import os
import time

# Function to get UUID of the SnapMirror relationship
def get_snapmirror_uuid():
	url = f"{base_url}/snapmirror/relationships/"
	response = requests.get(url, auth=(username, password), verify=False)
	if response.status_code == 200:
	    data = response.json()
	    if data.get("records"):
		return data["records"][0]["uuid"]  # Assuming you want the UUID of the first relationship
	return None

# Function to check the state of the SnapMirror relationship
def check_snapmirror_state(uuid):
	url = f"{base_url}/snapmirror/relationships/{uuid}"
	response = requests.get(url, auth=(username, password), verify=False)
	if response.status_code == 200:
	    data = response.json()
	    relationship_state = data.get("state")
	    return relationship_state
	return None

# Function to pause the SnapMirror relationship
def pause_snapmirror_relationship(uuid):
	url = f"{base_url}/snapmirror/relationships/{uuid}"
	payload = {"state": "paused"}
	response = requests.patch(url, json=payload, auth=(username, password), headers={"Content-Type": "application/json"}, verify=False)
	if response.status_code == 202:
	    print("SnapMirror relationship pause request accepted.")
	    return True
	else:
	    print("Failed to pause SnapMirror relationship.")
	    return False

# Function to break off the SnapMirror relationship
def break_snapmirror_relationship(uuid):
	url = f"{base_url}/snapmirror/relationships/{uuid}"
	payload = {"state": "broken_off"}
	response = requests.patch(url, json=payload, auth=(username, password), headers={"Content-Type": "application/json"}, verify=False)
	if response.status_code == 202:
	    print("SnapMirror relationship break request accepted.")
	    return True
	else:
	    print("Failed to break off SnapMirror relationship.")
	    return False


def lambda_handler(event, context):
    base_url = os.environ.get("NETAPP_BASE_URL")
    username = os.environ.get('NETAPP_USERNAME')  # Fetch username from environment variables
    password = os.environ.get('NETAPP_PASSWORD')  # Fetch password from environment variables

    # Main process
    snapmirror_uuid = get_snapmirror_uuid()
    if snapmirror_uuid:
        relationship_state = check_snapmirror_state(snapmirror_uuid)
        if relationship_state == "quiesced":
            print("SnapMirror relationship is already in a paused state (Quiesced).")
        else:
            if pause_snapmirror_relationship(snapmirror_uuid):
                print(f"Pausing SnapMirror relationship with UUID: {snapmirror_uuid}")
                time.sleep(30)  # Wait for 30 seconds after pausing
                if break_snapmirror_relationship(snapmirror_uuid):
                    print("SnapMirror relationship broken off successfully.")
                else:
                    print("Failed to break off SnapMirror relationship.")
            else:
                print("Failed to pause SnapMirror relationship.")
    else:
        print("No SnapMirror relationships found.")
    
    return '200'
