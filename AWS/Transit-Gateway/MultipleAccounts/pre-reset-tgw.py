import json, time, logging, boto3
from urllib.request import urlopen

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def validateEventPayload(event):
    for key in event.keys():
        if key == "body":
            logger.info("Found body parameter block")
            return json.loads(event[key])
    logger.info("Event does not has the body block")
    return event

def get_recovered_vpc_id(data_dictionary):
    url = data_dictionary["resourceMapping"]["recoveredMetadataPath"]
    response = urlopen(url)
    payload = json.loads(response.read())
    logger.info(payload)
    for item in payload:
        # Loop through the key-value pairs in each dictionary
        for _, value in item.items():
            # Check if the dictionary contains 'vpcId' key
            if 'vpcId' in value[0]:
                return value[0]['vpcId']
        else:
            return None

def delete_tgw_attachment(vpc_id, region):
    try:
        # Create an EC2 client
        ec2_client = boto3.client("ec2", region_name=region)

        # Describe Transit Gateway Attachments
        response = ec2_client.describe_transit_gateway_attachments(
            Filters=[
                {"Name": "resource-id", "Values": [vpc_id]},
                {"Name": "resource-type", "Values": ["vpc"]}
            ]
        )

        # Extract the Attachment ID if found
        attachments = response.get("TransitGatewayAttachments", [])
        if not attachments:
            print(f"No Transit Gateway Attachment found for VPC: {vpc_id}")
            return None

        for attachment in attachments:
            attachment_id = attachment.get("TransitGatewayAttachmentId")
            state = attachment.get("State")
            print(f"Transit Gateway Attachment found for the VPC {vpc_id}: Transit Gateway Attachment ID={attachment_id}, Transit Gateway Attachment State={state}")
            try:
                # Delete Transit Gateway Attachment
                ec2_client.delete_transit_gateway_vpc_attachment(TransitGatewayAttachmentId=attachment_id)
                print(f"Transit Gateway Attachment {attachment_id} deleted successfully.")
            except Exception as e:
                print(f"Error deleting attachment: {e}")
        
        time.sleep(10)
        return '200'
    except Exception as e:
        print(f"Error retrieving Transit Gateway Attachment: {e}")
        return '505'

def lambda_handler(event, context):
    data_dictionary = validateEventPayload(event)
    recovered_vpc_id = get_recovered_vpc_id(data_dictionary)
    recovery_region = data_dictionary["region"]
    if recovered_vpc_id!=None:
        return delete_tgw_attachment(recovered_vpc_id, recovery_region)
    else:
        return '505'
