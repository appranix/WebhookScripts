import requests
import logging
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from time import sleep
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import json

import azure.functions as func
from azure.identity import ClientSecretCredential
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def retrieve_json_from_azure_storage(container_name, file_name, connection_string):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name)

        json_bytes = blob_client.download_blob().readall()
        json_string = json_bytes.decode('utf-8')
        python_objects = json.loads(json_string)

        return python_objects
    except Exception as e:
        print(f"Error retrieving JSON data: {str(e)}")
        return None
    

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

        client_id       = "234342a8-eeeb-4e87-8b29-a6cfa4e1cec9"
        client_secret   = "Q4k8Q~YqdIJ4qa2OiBnDjpfaE5-hOxRvXFWkOaWO"
        tenant_id       = "976ace6a-6df4-47c0-9e7f-64dde4491107"
        
        connection_string = "DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName=apnxharistorageacc;AccountKey=9paDHTeh4COXVxHyupu8ous3nDS7w2DdJH3rN2YPosPkHweLAkcGS3W9JgR/aoOTW5EjBMTYlz89+AStwEq8vA==;BlobEndpoint=https://apnxharistorageacc.blob.core.windows.net/;FileEndpoint=https://apnxharistorageacc.file.core.windows.net/;QueueEndpoint=https://apnxharistorageacc.queue.core.windows.net/;TableEndpoint=https://apnxharistorageacc.table.core.windows.net/"
        container_name = "recovery-reset"
        file_name = f"{deployment_name}.json"

        # Retrieve the server_data from the blob
        server_data = retrieve_json_from_azure_storage(container_name, file_name, connection_string)
        replica_name=""
        if not server_data:
            logging.error("No server data found in the blob.")
            return func.HttpResponse(f"No server data found in the blob.",status_code=400)

        # Create Azure credentials
        credential = ClientSecretCredential(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id
        )

        for server_data in server_data:
            resource_group_name = server_data.get("source_resource_group_name")
            replica_server_name = server_data.get("replica_name")
            location = server_data.get("location")

            resource_client = ResourceManagementClient(credential, subscription_id)
            resources = resource_client.resources.list_by_resource_group(
                resource_group_name=resource_group_name,
                api_version="2022-09-01"
            )

            for id in list(resources):
                if id.type == "Microsoft.DBforPostgreSQL/flexibleServers" and id.name == replica_server_name:
                    logging.info("------------------------------")
                    server_name = id.name
                    server_location = id.location
                    logging.info(f"Server name: {server_name}")
                    logging.info(f"Server location: {server_location}")

                    access_token = credential.get_token("https://management.azure.com/.default").token

                    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBforPostgreSQL/flexibleServers/{server_name}/replicas?api-version=2023-03-01-preview"

                    headers = {
                        "Authorization": "Bearer " + access_token,
                        "Content-Type": "application/json"
                    }

                    response = requests.get(url, headers=headers)

                    if response.status_code == 200:
                        replicas = response.json().get("value", [])
                        for replica in replicas:
                            if replica["location"] == location:
                                replica_name = replica["name"]
                                logging.info("Replica name: %s", replica["name"])
                                logging.info("Replica ID: %s", replica["id"])
                                logging.info("Replica location: %s", replica["location"])
                                logging.info("------------------------------")
                    else:
                        logging.error("Failed to retrieve replicas: %s", response.text)

                    if replica_name == "":
                        logging.error(f"No Replicas Found in {location}")
                    else:
                        url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForPostgreSql/flexibleServers/{replica_name}?api-version=2023-03-01-preview"

                        payload = {
                            "properties": {
                                "ReplicationRole": "None"
                            }
                        }
                        response = requests.patch(url, headers=headers, json=payload)

                        if response.status_code in [200, 201, 202]:
                            logging.info("Replica server promotion initiated successfully")
                            logging.info("Waiting for Read Replica to promotion....")

                            sleep(60)

                            logging.info("Deletion of source server started...")
                            url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForPostgreSql/flexibleServers/{server_name}?api-version=2022-03-08-preview"
                            delete_response = requests.delete(url, headers=headers)
                            if delete_response.status_code in [200, 201, 202]:
                                logging.info("Deletion of Source server Initiated successfully")
                                return func.HttpResponse("200",status_code=200)
                            else:
                                logging.error("Failed to initiate the Deletion of Source server : %s", response.text)
                                return func.HttpResponse(f"Failed to initiate the Deletion of Source server",status_code=400)

                        else:
                            logging.error("Failed to update replica server: %s", response.text)
                            return func.HttpResponse(f"Failed to update replica server: { response.text}",status_code=400)
                    
        return func.HttpResponse(f"Error occurred:",status_code=400)
    
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return func.HttpResponse(f"Error occurred: {str(e)}",status_code=400)