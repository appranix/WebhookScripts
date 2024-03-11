from asyncio.log import logger

from cmath import log

import logging

import json

import requests

import traceback

import os

import azure.functions as func

from azure.storage.blob import BlobServiceClient
 

def main(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('Received request to update scaleset instance capacity')

    connection_string = os.getenv("connectionString")

    container_name = os.getenv("containerName")

    logging.debug(f"{connection_string}")

    logging.debug(f"{container_name}")

    try:
        recovery_id = req.get_json().get('recoveryId')

        blob_name=""

        if recovery_id:

            blob_name = recovery_id + ".json"        

        else:

            logging.info("Recovery Id not present in the request body.")

            raise Exception("RecoveryId not found in the content")        

        data = get_vmms_instance_count(req=req)                        

        logging.info(f"Data:  {data}")        

        if data and len(data) >0:

            scale_set_info= data

            logging.info(f"Final data to be written {scale_set_info}")

            blob_service_client = BlobServiceClient.from_connection_string(connection_string)            

            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
  

            logging.info("blob client created.")            

            blob_client.upload_blob(json.dumps(scale_set_info),overwrite=True)

            logger.info("Successfully upload.")            

            logging.info(" Adding tags")

            blob_client.set_blob_tags(tags={"processing_state":"pending"})

            logging.info("Done adding tags ")            

            return func.HttpResponse(status_code=200)            

        else:

            logging.error("Scale set info is not present in the bucket info")

            result = {"result" : "Failed with message:Scale set info is not present in the bucket"}

            return func.HttpResponse(json.dumps(result), mimetype="application/json", status_code=500)        

    except Exception as e:

        logging.error("Error in writting into blob with message " + e)        

        result = {"result" : "Failed with message:"+ e}

        return func.HttpResponse(json.dumps(result), mimetype="application/json",status_code=500)  

 
def get_vmms_instance_count(req):        

    recovered_metadata_json = None

    try:

        resource_mapping = req.get_json().get('resourceMapping')

        logging.debug(f"RESOURCE MAPPING = f{resource_mapping}")

        recovered_metadata_path_url = resource_mapping['recoveredMetadataPath']

        logging.debug(f"recovered_metadata_path_url = f{recovered_metadata_path_url}")

        recovered_metadata = requests.get(url = recovered_metadata_path_url)

        if recovered_metadata:

            logging.debug(f"recovered_metadata = {recovered_metadata}")        

            recovered_metadata_json = recovered_metadata.json()

            logging.debug(f"recovered_metadata_json = {recovered_metadata_json}")

        else:

            logging.info(f"recovered_metadata is empty : {recovered_metadata}")        


        if recovered_metadata_json:

            logging.info(f"recovered_metadata_json1 = ")

            for recovered_metadata  in recovered_metadata_json:

                logging.info(f"recovered_metadata_json 2= {recovered_metadata}")

                if recovered_metadata and "recoveredScalesetInitalCapacityMap" in recovered_metadata.keys() and recovered_metadata["recoveredScalesetInitalCapacityMap"]:

                    logging.info(f"recovered_metadata   {recovered_metadata}")

                    return recovered_metadata["recoveredScalesetInitalCapacityMap"]


    except Exception as ex:

        print(traceback.format_exc())

        logging.error(f"Exception while getting the metadata info {str(ex)}")

    return None