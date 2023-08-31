import requests
import logging
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from time import sleep
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import json
import os

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.function_name(name="HttpTrigger")
@app.route(route="", auth_level=func.AuthLevel.ANONYMOUS)
def HttpTrigger(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logging.info('Python HTTP trigger function processed a request.')
        request_json=req.get_json()
        deployment_name=request_json['recoveryName']
        primary_resource_metadata_url = request_json['resourceMapping']['primaryResourceMetadataPath']
        recovered_metadata_url = request_json['resourceMapping']['recoveredMetadataPath']
        # source_recovery_mapping_url = request_json['resourceMapping']['sourceRecoveryMappingPath']

        # Send GET requests and print the JSON responses
        json1 = requests.get(recovered_metadata_url).json()
        # print(json1)

        for item in json1:
            for key, value in item.items():
                for item_data in value:
                    recovery_resource_group = item_data['groupIdentifier']
                    recovery_region = item_data['region'].replace(' ', '').lower()
                    subscription_id = item_data['cloudResourceReferenceId'].split("/")[2]
                    break

        # Send GET requests and print the JSON responses
        json2 = requests.get(primary_resource_metadata_url).json()
        # print(json1)

        for item in json2:
            for key, value in item.items():
                for item_data in value:
                    resource_group_name = item_data['groupIdentifier']
                    location = item_data['region'].replace(' ', '').lower()
                    # recovery_subscription_id = item_data['cloudResourceReferenceId'].split("/")[2]
                    break

        client_id = os.environ["CLIENT_ID"]
        client_secret = os.environ["CLIENT_SECRET"]
        tenant_id = os.environ["TENANT_ID"]
        
        # Create a client secret credential object
        credential = ClientSecretCredential(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id
        )
        resource_client = ResourceManagementClient(credential, subscription_id)

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        resources = resource_client.resources.list_by_resource_group(
            resource_group_name=resource_group_name,
            api_version="2022-09-01"
        )
        replica_name=""
        logging.info("------------------------------")
        for id in list(resources):
            if id.type == "Microsoft.DBforMySQL/flexibleServers" and id.location == location:
                server_name = id.name
                server_location = id.location
                logging.info(f"Server name: {server_name}")
                logging.info(f"Server location: {server_location}")

                access_token = credential.get_token("https://management.azure.com/.default").token

                url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBforMySQL/flexibleServers/{server_name}/replicas?api-version=2022-01-01"

                headers = {
                    "Authorization": "Bearer " + access_token,
                    "Content-Type": "application/json"
                }

                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    replicas = response.json().get("value", [])
                    for replica in replicas:
                        if replica["location"].replace(" ","").lower() == recovery_region:
                            replica_name = replica["name"]
                            logging.info("Replica name: %s", replica["name"])
                            logging.info("Replica ID: %s", replica["id"])
                            logging.info("Replica location: %s", replica["location"])
                            logging.info("------------------------------")
                else:
                    logging.error("Failed to retrieve replicas: %s", response.text)

                if replica_name=="":
                    logging.error(f"No Replicas  Found in {recovery_region}")
                else:
                    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForMySQL/flexibleServers/{replica_name}?api-version=2022-01-01"

                    payload = {
                        "properties": {
                            "ReplicationRole": "None"
                        }
                    }
                    response = requests.patch(url, headers=headers, json=payload)

                    if response.status_code in [200,201,202]:
                        logging.info("Replica server promoted successfully.")
                        return func.HttpResponse("200")
                    else:
                        logging.error("Failed to update replica server: %s", response.text)
                        return func.HttpResponse(f"Failed to update replica server {response.text}. This HTTP triggered function executed successfully.",status_code=400)                
        return func.HttpResponse("200")
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return func.HttpResponse(f"Hello, {str(e)}. This HTTP triggered function executed successfully.",status_code=400)                
