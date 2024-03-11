import logging
import json
import traceback
import os
import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import Sku


def main(req: func.HttpRequest) -> func.HttpResponse:  
    logging.info(f"Received request for scaling VMSS instances. {req}")    
    connection_string = os.getenv("connectionString")
    container_name = os.getenv("containerName")
    logging.debug(f"{connection_string}")
    logging.debug(f"{container_name}")

    try:        
        # Get client details
        logging.debug("Getting blob service client")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(container_name)        
        logging.debug("Getting blob list with tag processing_state='pending' ")        

        # Get blobs by tags processing_state='pending'
        blobs_list = list(container_client.find_blobs_by_tags(f"processing_state='pending'"))        
        logging.info(f" blob_list size : {len(blobs_list)}")

        logging.info("Getting default credentials")
        token_credential = DefaultAzureCredential()    

        # Process all blobs
        for blob in blobs_list:

            # Get individual blob client.
            logging.info(f"Getting blob with name {blob.name}")
            blob_client = container_client.get_blob_client(blob.name)

            # Get blob content
            blob_data = get_blob_data(blob_client, blob)
            logging.info(f"Blob data: {blob_data}")

            if blob_data :
                errors = []
                # Iterate all the VMSS in th blob

                for vmss in blob_data :
                    update_scale_set_capacity(token_credential=token_credential, vmss=vmss, blob_data=blob_data, errors=errors)

                # If there are any errors  don't udpate the blob.
                if len(errors) ==0:
                    blob_client.set_blob_tags(tags={"processing_state":"completed"})
                else:
                    logging.error(f"{len(errors)} VMSS scaling failed.")
            else:
                logging.error(f"Blob data is empty")

        # set metadata to "myblob" of container "mycontainer"
        return func.HttpResponse(status_code=200)

    except Exception as e:        
        print(traceback.format_exc())
        logging.error("Error in getting blob service client" + str(e))        
        result = {"result" : "Failed with message:"+ str(e)}
        return func.HttpResponse(json.dumps(result), mimetype="application/json",status_code=500)


def get_blob_data(blob_client, blob):    
    # Donwload blob content
    blob_data = blob_client.download_blob()                
    logging.debug(f"Data Downloaded")

    # Read blob contents
    return json.loads(blob_data.readall())

def update_scale_set_capacity(token_credential,vmss, blob_data, errors ):
    try:
        # Get details and        
        scaleset_capacity = None
        scaleset_capacity = blob_data[vmss]
        if scaleset_capacity:            
            logging.info(f"Updating the instance {vmss} to capacity: {scaleset_capacity}")
            subscriptionstringfind = vmss.split("/")
            subscription_id = subscriptionstringfind[2]
            rg_name = subscriptionstringfind[4]
            scaleset_name = subscriptionstringfind[-1]                        
            logging.info(f"Getting ComputeManagementClient")            
            compute_vmss_client = ComputeManagementClient(token_credential, subscription_id)
            logging.info(f"Getting scalesetdetails")            
            scalesetdetails = compute_vmss_client.virtual_machine_scale_sets.get(rg_name, scaleset_name)
            logging.info(f"Setting SKU for with capacity ")            
            scalesetdetails.sku = Sku(name =scalesetdetails.sku.name, capacity = scaleset_capacity)    

            poller = compute_vmss_client.virtual_machine_scale_sets.begin_create_or_update(rg_name,\
            scalesetdetails.name, scalesetdetails)            
            logging.info(f"The instance {vmss} update with the capacity: {scaleset_capacity}  successfully. ")            

    except Exception as ex:
        logging.error(f"Exception while updating the instance {vmss} capacity {scaleset_capacity} with message {ex} ")
        errors.append("vmss")