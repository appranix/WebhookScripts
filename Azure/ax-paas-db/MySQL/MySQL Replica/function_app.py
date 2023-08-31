import requests
import logging
from azure.mgmt.resource import ResourceManagementClient
from time import sleep
from azure.storage.blob import BlobServiceClient
import json
import os
import azure.functions as func
from azure.identity import ClientSecretCredential
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.function_name(name="HttpTrigger")
@app.route(route="", auth_level=func.AuthLevel.ANONYMOUS)
def HttpTrigger(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logging.info('Python HTTP trigger function processed a request.')
        export_data = []
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

        # Retrieve all resources in the specified resource group and location
        resources = resource_client.resources.list_by_resource_group(
            resource_group_name=resource_group_name,
            api_version="2022-09-01"
        )

        # Initialize variable to store replica name
        replica_name = ""
        logging.info("------------------------------")

        # Loop through the resources to find MySQL replicas in the specified location
        for resource in resources:
            if resource.type.lower() == "Microsoft.DBforMySQL/flexibleServers".lower() and resource.location == location:
                server_name = resource.name
                server_location = resource.location
                logging.info(f"Server name: {server_name}")
                logging.info(f"Server location: {server_location}")

                # Get access token for the management API
                access_token = credential.get_token("https://management.azure.com/.default").token

                # Create the URL to retrieve replicas
                url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBforMySQL/flexibleServers/{server_name}/replicas?api-version=2022-01-01"
                headers = {
                    "Authorization": "Bearer " + access_token,
                    "Content-Type": "application/json"
                }

                # Send GET request to retrieve replicas
                response = requests.get(url, headers=headers)

                if response.status_code == 200:
                    replicas = response.json().get("value", [])
                    for replica in replicas:
                        logging.info(replica["name"])
                        logging.info(replica["location"])
                        if replica["location"].replace(' ', '').lower() == recovery_region:
                            replica_name = replica["name"]
                            logging.info("Replica name: %s", replica["name"])
                            logging.info("Replica ID: %s", replica["id"])
                            logging.info("Replica location: %s", replica["location"])
                            logging.info("------------------------------")
                else:
                    logging.error("Failed to retrieve replicas: %s", response.text)

                if replica_name == "":
                    logging.error(f"No Replicas Found in {recovery_region}")
                else:
                    # Initiate promotion of the replica to become the primary server
                    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForMySql/flexibleServers/{replica_name}?api-version=2022-01-01"

                    payload = {
                        "properties": {
                            "ReplicationRole": "None"
                        }
                    }
                    response = requests.patch(url, headers=headers, json=payload)

                    if response.status_code in [200, 201, 202]:
                        logging.info("Replica server promotion initiated successfully")
                        logging.info("Waiting for Read Replica to promotion....")

                        sleep(30)

                        logging.info("Deletion of source server started...")
                        url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForMySql/flexibleServers/{server_name}?api-version=2021-05-01"
                        delete_response = requests.delete(url, headers=headers)
                        if delete_response.status_code in [200, 201, 202]:
                            logging.info("Deletion of Source server Initiated successfully")
                        else:
                            logging.error("Failed to initiate the Deletion of Source server : %s", response.text)

                        rec_replica_name = "replica-" + replica_name

                        logging.info("Starting the creation of replica server in Source region %s", location)

                        # Create a new replica server in the source region
                        url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForMySql/flexibleServers/{rec_replica_name}?api-version=2021-05-01"
                        payload = {
                            "location": f"{location}",
                            "properties": {
                                "createMode": "Replica",
                                "SourceServerResourceId": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBForMySql/flexibleServers/{replica_name}"
                            }
                        }

                        create_response = requests.put(url, headers=headers, json=payload)
                        if create_response.status_code in [200, 201, 202]:
                            logging.info("Creation of Read Replica in the source region is Initiated successfully")

                        else:
                            logging.error("Failed to initiate the creation of Read Replica in the source region : %s", response.text)
                            return func.HttpResponse(f"Failed to initiate the creation of Read Replica in the source region",status_code=400)

                    else:
                        logging.error("Failed to update replica server: %s", response.text)
                        return func.HttpResponse(f"Failed to update replica server",status_code=400)

                    # Store server data for export
                    server_data = {
                        "server_name": server_name,
                        "replica_name": replica_name,
                        "location": server_location,
                        "recovery_region": recovery_region,
                        "source_resource_group_name": resource_group_name
                    }

                    export_data.append(server_data)
        if export_data!=[]:
            # Convert export data to JSON format
            json_data = json.dumps(export_data)

            # Connect to Azure Storage and store the JSON data in a blob
            connection_string = os.environ["STORAGE_STRING"]
            container_name = "recovery-reset"
            file_name = f"{deployment_name}.json"

            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            container_client = blob_service_client.get_container_client(container_name)
            blob_client = container_client.get_blob_client(file_name)

            blob_client.upload_blob(json_data, overwrite=True)

            logging.info("Data stored in Azure Storage successfully.")

        return func.HttpResponse(
                "200",
                status_code=200)
    
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return func.HttpResponse(f"Error : {str(e)}",status_code=400)
