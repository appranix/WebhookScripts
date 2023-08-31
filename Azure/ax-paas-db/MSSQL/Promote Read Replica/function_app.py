import azure.functions as func
import logging
import os
import logging
import requests
from azure.identity import ClientSecretCredential
from azure.mgmt.sql import SqlManagementClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logging.basicConfig(level=logging.WARNING)

@app.route(route="HttpTrigger", auth_level=func.AuthLevel.ANONYMOUS)
def HttpTrigger(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logging.warning('Python HTTP trigger function processed a request.')
        request_json=req.get_json()
        deployment_name=request_json['recoveryName']
        primary_resource_metadata_url = request_json['resourceMapping']['primaryResourceMetadataPath']
        recovered_metadata_url = request_json['resourceMapping']['recoveredMetadataPath']
        # source_recovery_mapping_url = request_json['resourceMapping']['sourceRecoveryMappingPath']
        logging.warning(request_json)
        # Send GET requests and print the JSON responses
        json1 = requests.get(recovered_metadata_url).json()
        logging.warning(json1)

        for item in json1:
            for key, value in item.items():
                for item_data in value:
                    recovery_resource_group = item_data['groupIdentifier']
                    recovery_region = item_data['region'].replace(
                        ' ', '').lower()
                    subscription_id = item_data['cloudResourceReferenceId'].split(
                        "/")[2]
                    break

      # Send GET requests and print the JSON responses
        json2 = requests.get(primary_resource_metadata_url).json()
        logging.warning(json2)

        for item in json2:
            for key, value in item.items():
                for item_data in value:
                    resource_group_name = item_data['groupIdentifier']
                    recovery_resource_group = deployment_name+"-"+resource_group_name
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

        # Create an instance of the SQL management client
        sql_client = SqlManagementClient(credential, subscription_id)

        # List all Microsoft SQL servers in the recovery resource group
        servers = sql_client.servers.list_by_resource_group(resource_group_name)
        logging.warning(f"Listing all Microsoft SQL servers in the recovery resource group '{resource_group_name}'")
        
        resetsql=False
        if "resetUser" in request_json:
            location,recovery_region=recovery_region,location
            resetsql=True
            logging.warning("Reset")

        sql_dict={}
        # Iterate over each server
        for server in servers:
            if server.location==location:
                logging.warning(f"Checking server '{server.name}' for read replicas")
                # List the read replicas for the server
                replicas = sql_client.replication_links.list_by_server(resource_group_name, server.name)
                
                # Iterate over each replica
                for replica in replicas:
                    logging.warning(f"Checking replica '{replica.partner_server}' located in '{replica.partner_location}'")
                    # Check if the replica is located in the recovery region
                    if replica.partner_location.replace(' ','').lower() == recovery_region:
                        logging.warning(f"Promoting replica '{replica.partner_server}' to become the primary server")
                        
                        # Promote the replica to become the primary server
                        sql_client.replication_links.begin_failover(
                            resource_group_name,
                            replica.partner_server,
                            replica.partner_database,
                            replica.name
                        )  
                    sql_dict[server.name] = replica.partner_server

                    logging.warning(f"Promoted replica '{replica.partner_server}' of server '{server.name}' to become the primary server")
                else:
                    logging.warning(f"Replica '{replica.partner_server}' of server '{server.name}' is not located in the recovery region")
        else:
            logging.warning(f"Server '{server.name}' is not located in the source region")

        if resetsql:
            return func.HttpResponse(
                    "200",
                    status_code=200)

        logging.warning(f"Promoted Servers With Replica {sql_dict}")

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        return func.HttpResponse(f"Error occurred: {str(e)}\n. This HTTP triggered function executed successfully.",status_code=400)
    return func.HttpResponse(
                    "200",
                    status_code=200)
