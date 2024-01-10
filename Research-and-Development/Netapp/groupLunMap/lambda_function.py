import os
import requests
import json
import base64

def lambda_handler(event, context):
    # Retrieve environment variables
    base_url = os.getenv('BASE_URL')
    auth_credentials = os.getenv('AUTH_CREDENTIALS')
    igroup_name = os.getenv('IGROUP_NAME')
    initiator_name = os.getenv('INITIATOR_NAME')
    svm_name = os.getenv('SVM_NAME')
    lun_id = os.getenv('LUN_ID')
    lun_path = os.getenv('LUN_PATH')

    # Define headers for the HTTP request
    headers = {
        "accept": "application/json",
        "authorization": f"Basic {base64.b64encode(auth_credentials.encode()).decode()}",
        "content-type": "application/json"
    }

    # Define the payload for creating an igroup
    igroup_payload = {
        "name": igroup_name,
        "protocol": "mixed",
        "os_type": "windows",
        "initiators": [initiator_name],
        "svm": svm_name
    }

    # Send the HTTP request to create the igroup
    response = requests.post(f"{base_url}/protocols/san/igroups", headers=headers, data=json.dumps(igroup_payload))

    # Check if the igroup was created successfully
    if response.status_code == 201:
        print("Igroup created successfully.")
    else:
        print(f"Failed to create igroup. Status code: {response.status_code}, Error: {response.json()}")

    # Define the payload for mapping a LUN to the igroup
    lun_map_payload = {
        "igroup": igroup_name,
        "lun_id": lun_id,
        "lun": lun_path,
        "svm": svm_name
    }

    # Send the HTTP request to map the LUN to the igroup
    response = requests.post(f"{base_url}/protocols/san/lun-maps", headers=headers, data=json.dumps(lun_map_payload))

    # Check if the LUN was mapped successfully
    if response.status_code == 201:
        print("LUN mapped successfully.")
    else:
        print(f"Failed to map LUN. Status code: {response.status_code}, Error: {response.json()}")

    return {
        'statusCode': response.status_code,
        'body': json.dumps('Function execution completed.')
    }

