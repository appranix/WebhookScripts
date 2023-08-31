import requests
import logging
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient


import azure.functions as func
import logging
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
from azure.identity import ClientSecretCredential

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
                    recovery_region = item_data['region']
                    subscription_id = item_data['cloudResourceReferenceId'].split("/")[2]
                    break

        # Send GET requests and print the JSON responses
        json2 = requests.get(primary_resource_metadata_url).json()
        # print(json1)

        for item in json2:
            for key, value in item.items():
                for item_data in value:
                    resource_group_name = item_data['groupIdentifier']
                    location = item_data['region']
                    # recovery_subscription_id = item_data['cloudResourceReferenceId'].split("/")[2]
                    break

        client_id       = "234342a8-eeeb-4e87-8b29-a6cfa4e1cec9"
        client_secret   = "Q4k8Q~YqdIJ4qa2OiBnDjpfaE5-hOxRvXFWkOaWO"
        tenant_id       = "976ace6a-6df4-47c0-9e7f-64dde4491107"
        
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
        snapshots=""
        logging.info("------------------------------")
        for id in list(resources):
            if id.type == "Microsoft.DBforMySQL/flexibleServers" and id.location == location:
                server_name = id.name
                server_location = id.location
                logging.info(f"Server name: {server_name}")
                logging.info(f"Server location: {server_location}")

                access_token = credential.get_token("https://management.azure.com/.default").token

                url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBforMySQL/flexibleServers/{server_name}/backups?api-version=2022-01-01"

                headers = {
                    "Authorization": "Bearer " + access_token,
                    "Content-Type": "application/json"
                }

                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    snapshots = response.json().get("value", [])

                if not snapshots:
                    logging.info(f"No backups found for {server_name}")
                else:
                    latest_snapshot = max(snapshots, key=lambda x: x["properties"]["completedTime"])
                    restore_point_time = latest_snapshot["properties"]["completedTime"]
                    recovery_server_name = deployment_name + server_name
                    print(restore_point_time)
                    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBforMySQL/flexibleServers/{recovery_server_name}?api-version=2021-05-01"
                    payload = {
                                "location": location,
                                "properties": {
                                    "createMode": "PointInTimeRestore",
                                    "sourceServerResourceId": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.DBforMySQL/flexibleServers/{server_name}",
                                    "restorePointInTime":restore_point_time
                                }
                            }
                    response = requests.put(url, headers=headers, json=payload)
                    if response.status_code in [200, 201, 202]:
                        logging.info(f"Response code {response.status_code}")
                        logging.info("PITR server creation Initiated")
                        return func.HttpResponse("200")
                    else:
                        logging.error("Failed to create PITR server: %s", response.text)
                        return func.HttpResponse(f"Failed to create PITR server. This HTTP triggered function executed successfully.",status_code=400)


        return func.HttpResponse("200")
            
    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return func.HttpResponse(f"Hello, {str(e)}. This HTTP triggered function executed successfully.",status_code=400)







