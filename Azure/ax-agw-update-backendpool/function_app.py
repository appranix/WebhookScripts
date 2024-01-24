import azure.functions as func
import logging, requests, json, os, requests
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient,ContentSettings
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.keyvault.secrets import SecretClient

# Define your Azure Storage account connection string and blob details
storage_connection_string = os.getenv("STORAGE_CONNECTION_STRING")
container_name = os.getenv("STORAGE_CONTAINER")
tenant_id = os.getenv("TENANT_ID")
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")

dr_midentity_resource_id = os.getenv("DR_MIDENTITY_RESOURCE_ID")
dr_keyvault_name = os.getenv("DR_KEYVAULT_NAME")
primary_keyvault_name = os.getenv("PRIMARY_KEYVAULT_NAME")
dr_keyvault_uri = f"https://{dr_keyvault_name}.vault.azure.net/"

# Get a credential object using the ClientSecretCredential
credential = ClientSecretCredential(tenant_id, client_id, client_secret)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

## App Gateway Info extract script
@app.route(route="get_app_gateway_info")
def get_app_gateway_info(req: func.HttpRequest) -> func.HttpResponse:
    logging.warning('Python HTTP trigger function processed a request to get info.')
    
    try:
        request_json = req.get_json()
        logging.warning(request_json)
        
        recovery_name = request_json.get('recoveryName', '')
        blob_name = f'{recovery_name}_recovery_payload.json'
        upload_info(storage_connection_string, container_name, blob_name, request_json)
        
        source_metadata_url = request_json['resourceMapping']['primaryResourceMetadataPath']

        # Send a GET request and parse the JSON response
        response = requests.get(source_metadata_url)
        if response.status_code == 200:
            source_resource_details = response.json()
        else:
            logging.error(f"Failed to retrieve data from {source_metadata_url}. Status code: {response.status_code}")

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}") 
    
    get_resource_group(recovery_name, source_resource_details)
    get_app_gateway_info(source_resource_details)
    
    return func.HttpResponse("200")

def get_app_gateway_info(payload):
    blob_name = "app_gateway_mapper.json"
    app_gw_mapper = read_info(storage_connection_string, container_name, blob_name, default_value={})
    if isinstance(payload, list):
        for resource in payload:
            if "APPLICATION_GATEWAY" in resource:
                for item in resource["APPLICATION_GATEWAY"]:
                    app_gate_name = item['cloudResourceReferenceId']
                    for key,value in item.items():
                        if key=='additionalAttributes':
                            affiliated_resource = value.get("AFFILIATED_RESOURCE")
                            for resource_item in affiliated_resource:
                                if resource_item['type'] in ["VIRTUAL_MACHINE_SCALE_SET", "NETWORK_INTERFACE"]:
                                    if resource_item:
                                        be_pool_name = resource_item['backendPoolName']
                                        be_pool_id = app_gate_name + "/backendAddressPools/" + be_pool_name
                                        resource_id = resource_item['resourceId']
                                        if be_pool_id not in app_gw_mapper.keys():
                                            app_gw_mapper[be_pool_id] = [resource_id]
                                        else:
                                            if resource_id not in app_gw_mapper[be_pool_id]:
                                                app_gw_mapper[be_pool_id].append(resource_id)

    logging.warning(app_gw_mapper)
    
    upload_info(storage_connection_string, container_name, blob_name, app_gw_mapper)

def read_info(storage_connection_string, container_name, blob_name, default_value={}):
    blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)

    # Get or create the container
    container_client = blob_service_client.get_container_client(container_name)
    if not container_client.exists():
        logging.warning(f"Container {container_name} doesn't exists.")
        container_client.create_container()

    blob_client = container_client.get_blob_client(blob_name)
    try:
        content = blob_client.download_blob().readall()
        return json.loads(content)
    except Exception as e:
        # Create the blob with the default value if it doesn't exist
        logging.warning(f"Blob {blob_name} doesn't exists in the container {container_name}.")
        content = json.dumps(default_value)
        blob_client.upload_blob(content, overwrite=True, content_settings=ContentSettings(content_type="application/json"))
        return default_value

# Function to write the updated rg_mapping_dict to a blob in the storage account
def upload_info(storage_connection_string, container_name, blob_name, rg_mapping_dict):
    blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
        
    container_client = blob_service_client.get_container_client(container_name)
    if not container_client.exists():
        container_client.create_container()
    
    blob_client = container_client.get_blob_client(blob_name)
    content = json.dumps(rg_mapping_dict,indent=4)
    blob_client.upload_blob(content, overwrite=True, content_settings=ContentSettings(content_type="application/json"))
    logging.warning(f"Uploaded the {blob_name} to the container {container_name}")
    
def get_resource_group(recovery_name, source_resource_details):
    blob_name = "resource_group_mapper.json"
    rg_mapping_dict = read_info(storage_connection_string, container_name, blob_name, default_value={})

    for resource_object in source_resource_details:
        rg_values = resource_object.get('RESOURCE_GROUP', [])
        for each_rg_object in rg_values:
            src_rg_name = each_rg_object.get('name', '')
            if src_rg_name:
                rg_mapping_dict[src_rg_name] = f"{recovery_name}-{src_rg_name}"

    logging.warning(f"Updated Resource Group Mapping: {rg_mapping_dict}")

    upload_info(storage_connection_string, container_name, blob_name, rg_mapping_dict)


## App Gateway backend pool attachment script
@app.route(route="attach_app_gateway_backendpool", auth_level=func.AuthLevel.ANONYMOUS)
def attach_app_gateway_backendpool(req: func.HttpRequest) -> func.HttpResponse:
        
    request_json = req.get_json()
    logging.warning(request_json)
    
    replacement_dict = read_attachment_info(storage_connection_string, container_name, blob_name='resource_group_mapper.json', default_value={})
    content = read_attachment_info(storage_connection_string, container_name, blob_name='app_gateway_mapper.json', default_value={})
    
    for key, value in replacement_dict.items():
        content = json.dumps(content)
        content = content.replace('/' + key + '/', '/' + value + '/')
        content = json.loads(content)
    try:
        # Loop through the content_dict and classify each resource
        content_dict = json.loads(json.dumps(content))  # Ensure content is a dictionary
        for key, value in content_dict.items():
            for item in value:
                try:
                    if "virtualMachineScaleSets" in item:
                        attach_pool_to_vmss(item, key)
                    elif "networkInterfaces" in item:
                        attach_pool_to_nic(item, key)
                except Exception as e:
                    logging.error(f"Exception: {e} \n Unable to attach {item} to {key}")
                    
    except Exception as e:
        logging.error(f"Something went wrong {e}")
        return func.HttpResponse("500")
    return func.HttpResponse("200")

def attach_pool_to_nic(nic_id, pool_id):
    # Extract necessary information from the NIC and pool IDs
    subscription_id = nic_id.split('/')[2]
    resource_group_name = nic_id.split('/')[4]
    nic_name = nic_id.split('/')[-1]

    gateway_name = pool_id.split('/')[-3]
    pool_name = pool_id.split('/')[-1]
    pool_resource_group_name=pool_id.split('/')[4]
    
    # Instantiate a network management client
    network_client = NetworkManagementClient(credential, subscription_id)

    # Get the NIC
    nic = network_client.network_interfaces.get(resource_group_name, nic_name)

    # Get the Application Gateway
    gateway = network_client.application_gateways.get(pool_resource_group_name, gateway_name)

    # Find the backend address pool in the Application Gateway's backend address pools
    pool = next((pool for pool in gateway.backend_address_pools if pool.name == pool_name), None)

    if pool is not None:
        # Initialize application_gateway_backend_address_pools as a list if it's None
        if nic.ip_configurations[0].application_gateway_backend_address_pools is None:
            nic.ip_configurations[0].application_gateway_backend_address_pools = []

        # Attach the backend pool to the NIC
        nic.ip_configurations[0].application_gateway_backend_address_pools.append(pool)

        # Update the NIC
        network_client.network_interfaces.begin_create_or_update(resource_group_name, nic_name, nic)
        logging.warning(f"{nic_name} attached to {pool_name} in {gateway_name}")
    else:
        logging.error(f"Backend address pool {pool_name} not found in Application Gateway {gateway_name}.")

def attach_pool_to_vmss(vmss_id, pool_id):
    
    # Extract necessary information from the VMSS and pool IDs
    subscription_id = vmss_id.split('/')[2]
    resource_group_name = vmss_id.split('/')[4]
    vmss_name = vmss_id.split('/')[-1]

    gateway_name = pool_id.split('/')[-3]
    pool_name = pool_id.split('/')[-1]
    pool_resource_group_name=pool_id.split('/')[4]
    
    # Instantiate a compute management client
    compute_client = ComputeManagementClient(credential, subscription_id)
    
    # Instantiate a network management client
    network_client = NetworkManagementClient(credential, subscription_id)

    # Get the VMSS
    vmss = compute_client.virtual_machine_scale_sets.get(resource_group_name, vmss_name)

    # Get the Application Gateway
    gateway = network_client.application_gateways.get(pool_resource_group_name, gateway_name)

    # Find the backend address pool in the Application Gateway's backend address pools
    pool = next((pool for pool in gateway.backend_address_pools if pool.name == pool_name), None)

    if pool is not None:
        # Initialize application_gateway_backend_address_pools as a list if it's None
        if vmss.virtual_machine_profile.network_profile.network_interface_configurations[0].ip_configurations[0].application_gateway_backend_address_pools is None:
            vmss.virtual_machine_profile.network_profile.network_interface_configurations[0].ip_configurations[0].application_gateway_backend_address_pools = []

        # Attach the backend pool to the VMSS
        vmss.virtual_machine_profile.network_profile.network_interface_configurations[0].ip_configurations[0].application_gateway_backend_address_pools.append(pool)

        # Update the VMSS
        compute_client.virtual_machine_scale_sets.begin_create_or_update(resource_group_name, vmss_name, vmss)
        logging.warning(f"{vmss_id} attached to {pool_name} in {gateway_name}")
    else:
        logging.error(f"Backend address pool {pool_name} not found in Application Gateway {gateway_name}.")

def read_attachment_info(storage_connection_string, container_name, blob_name, default_value={}):
    blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)

    # Get or create the container
    container_client = blob_service_client.get_container_client(container_name)
    if not container_client.exists():
        logging.warning(f"Container {container_name} doesn't exists")

    blob_client = container_client.get_blob_client(blob_name)
    try:
        content = blob_client.download_blob().readall()
        return json.loads(content)
    except Exception as e:
        # Handle the case when the blob doesn't exist
        logging.warning(f"Blob {blob_name} doesn't exists in the container {container_name}")
        return json.loads(default_value)

## Update App Gateway SSL Cert script
@app.route(route="update_app_gateway_ssl_cert", auth_level=func.AuthLevel.ANONYMOUS)
def update_app_gateway_ssl_cert(req: func.HttpRequest) -> func.HttpResponse:
    logging.warning('Python HTTP trigger function processed a request to update the SSL Certificate.')
    
    try:
        subscription_id = dr_midentity_resource_id.split('/')[2]
        network_client = NetworkManagementClient(credential, subscription_id)
        bep_resource_id = read_attachment_info(storage_connection_string, container_name, blob_name='app_gateway_mapper.json', default_value={})
        updated_agw = []
        for resource_id in bep_resource_id.keys():
            application_gateway_name, resource_group_name = extract_resource_info(resource_id)
            if application_gateway_name not in updated_agw:
                application_gateway = network_client.application_gateways.get(
                    resource_group_name,
                    application_gateway_name
                )
                logging.warning(f"Found Application Gateway '{application_gateway_name}' in Resource Group '{resource_group_name}' and region '{application_gateway.location}'")
                
                if application_gateway.identity and application_gateway.identity.user_assigned_identities:
                    # Find the current identity
                    current_identity = list(application_gateway.identity.user_assigned_identities.keys())[0]

                    logging.warning(f"Current Identity for {application_gateway_name}: {current_identity}")
                    
                    # Replace it with a new identity (replace 'new_identity_resource_id' with the new identity's resource ID)
                    new_identity_resource_id = dr_midentity_resource_id
                    application_gateway.identity.user_assigned_identities = {new_identity_resource_id: {}}
            
                    logging.warning(f"Updating Identity for {application_gateway_name}: {new_identity_resource_id}")
                
                for certificate in application_gateway.ssl_certificates:
                    logging.error(f"{certificate}......{certificate.name}")
                    new_cert_name = certificate.key_vault_secret_id.split('/')[-1]                  
                    
                    if is_certificate_in_dr_keyvault(new_cert_name):
                        new_vault_secret_id = certificate.key_vault_secret_id.replace(primary_keyvault_name, dr_keyvault_name)
                        # If the secret ID is updated and the certificate is in DR Key Vault, redeploy the Application Gateway
                        certificate.key_vault_secret_id = new_vault_secret_id
                        logging.warning(f"Updated active SSL certificate Key Vault secret ID: {certificate.key_vault_secret_id}")
                deploy_app_gateway(network_client, resource_group_name, application_gateway_name, application_gateway)
                updated_agw.append(application_gateway_name)
        
    except Exception as e:
        logging.error(f"Something went wrong {e}")
        return func.HttpResponse("500")
    return func.HttpResponse("200")

def is_certificate_in_dr_keyvault(new_cert_name):
    secret_client = SecretClient(vault_url=dr_keyvault_uri, credential=credential)
    try:
        secret_client.get_secret(new_cert_name)
        logging.warning(f"The secret '{new_cert_name}' exists in the Key Vault {dr_keyvault_uri}.")
        return True
    except Exception as e:
        logging.warning(f"The secret '{new_cert_name}' does not exist in the Key Vault {dr_keyvault_uri}. Error: {str(e)}")
        return False
    
def extract_resource_info(resource_id):
    resource_group_mapper = read_attachment_info(storage_connection_string, container_name, blob_name='resource_group_mapper.json', default_value={})
    parts = resource_id.split('/')
    
    # Find the index of 'resourceGroups' and 'applicationGateways' in the parts list
    rg_index = parts.index('resourceGroups')
    agw_index = parts.index('applicationGateways')

    # Extract the Resource Group name and Application Gateway name
    resource_group_name = parts[rg_index + 1]
    application_gateway_name = parts[agw_index + 1]
    
    return application_gateway_name, resource_group_mapper[resource_group_name]
    
def deploy_app_gateway(network_client, resource_group_name, application_gateway_name, application_gateway):
    try:
        async_operation = network_client.application_gateways.begin_create_or_update(
                resource_group_name=resource_group_name,
                application_gateway_name=application_gateway_name,
                parameters=application_gateway
            )
        async_operation.result()
        logging.warning(f"Application Gateway {application_gateway_name} redeployment successful.")
    except Exception as e:
        logging.warning(f"Exception occured while redeploying the {application_gateway_name}. Error: {str(e)}")