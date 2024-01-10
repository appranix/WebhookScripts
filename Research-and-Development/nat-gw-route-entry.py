import boto3, json
from urllib.request import urlopen
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def validateEventPayload(event):
    for key in event.keys():
        if key == "body":
            logger.info("Found body parameter block")
            return json.loads(event[key])
    logger.info("Event does not has the body block")
    return json.loads(event)

def extract_payload(event):
    try:
        data_dictionary = validateEventPayload(event)
        logger.info(data_dictionary["recoveryStatus"])
        if data_dictionary["recoveryStatus"] == "RECOVERY_COMPLETED":
            url = data_dictionary["resourceMapping"]["recoveredMetadataPath"]
            response = urlopen(url)
            payload = json.loads(response.read())
            logger.info(payload)
            return payload
        else:
            logger.error("Unable to find the body...")
            return None
        
    except Exception as e:
        logger.error(f"FAILED with Exception {e}")
        return None

def extract_vpcId_and_natGatewayId(payload):
    
    print(type(payload), payload)
    extracted_data = ()
    
    for item in payload:
        if "NAT_GATEWAYS" in item:
            for nat_gateway in item["NAT_GATEWAYS"]:
                for key, value in nat_gateway.items():
                    return nat_gateway["vpcId"], nat_gateway["natGatewayId"]
    return extracted_data

def get_private_subnet_route_tables(vpc_id):
    """
    Retrieve all private subnet route tables for a given VPC.
    """
    client = boto3.client('ec2')
    
    # Get all subnets in the VPC
    response = client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    subnet_ids = [subnet['SubnetId'] for subnet in response['Subnets']]
    
    # Get the route tables associated with each subnet
    route_tables = []
    for subnet_id in subnet_ids:
        subnet_response = client.describe_route_tables(Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}])
        route_tables.extend(subnet_response['RouteTables'])
    
    return route_tables

def add_nat_gateway_route(route_table_id, nat_gateway_id):
    """
    Add a route entry for NAT Gateway to the given route table.
    """
    client = boto3.client('ec2')
    print(f"Adding NAT Gateway {nat_gateway_id} route to {route_table_id}.........")
    
    try:
        response = client.create_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock='0.0.0.0/0',
            NatGatewayId=nat_gateway_id
        )
        
        print(f"Added NAT Gateway route to {route_table_id}")
    except Exception as e:
        print(f"Unable to add NAT Gateway route to {route_table_id}.Error: {e}")

def lambda_handler(event, context):    
    
    payload = extract_payload(event)
    
    vpc_id,nat_gateway_id = extract_vpcId_and_natGatewayId(payload)
    print(vpc_id,nat_gateway_id)
    
    route_tables = get_private_subnet_route_tables(vpc_id)
    
    for route_table in route_tables:
        add_nat_gateway_route(route_table['RouteTableId'], nat_gateway_id)
        print(f"Added {nat_gateway_id} in the route {route_table['RouteTableId']}")
    return {
        "statusCode": 200
    }
