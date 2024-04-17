import json
import boto3
import time
from urllib.request import urlopen
import os

def lambda_handler(event, context):
    request_json = json.loads(event['body'])
    print(request_json)
    query_params = event['queryStringParameters']
    transit_gateway_id=query_params['transit_gateway_id']
    transit_gateway_route_table_id=query_params['tgw_route_table_id']
    
    # prefix=request_json['recoveryName']
    # primary_resource_metadata_url = request_json['resourceMapping']['primaryResourceMetadataPath']
    # recovered_metadata_url = request_json['resourceMapping']['recoveredMetadataPath']
    source_recovery_mapping_url = request_json['resourceMapping']['sourceRecoveryMappingPath']
    protectionTimelineId=request_json["timelineDetails"]["protectionTimelineId"]

    # # Send GET requests and print the JSON responses
    # json1 = requests.get(recovered_metadata_url).json()
    # # print(json1) 

    # for item in json1:
    #     for key, value in item.items():
    #         for item_data in value:
    #             recovery_resource_group = item_data['groupIdentifier']
    #             recovery_region = item_data['region']
    #             break

    # # Send GET requests and print the JSON responses
    # json2 = requests.get(primary_resource_metadata_url).json()
    # # print(json1)

    # for item in json2:
    #     for key, value in item.items():
    #         for item_data in value:
    #             resource_group_name = item_data['groupIdentifier']
    #             location = item_data['region']
    #             break

    # Send GET requests and print the JSON responses
    json3 = json.loads(urlopen(source_recovery_mapping_url).read())
    
    print(json3)

    vpc_ids=[]
    # Loop through the VPCs and print their IDs
    for entry in json3:
        if "VPC" in entry:
            vpcs_list = entry["VPC"]
            for vpcs in vpcs_list:
                for vpc in vpcs:
                    region=vpcs[vpc]["destination"]["region"]
                    vpc_id=vpcs[vpc]["destination"]["vpcId"]
                    source_vpc_id=vpcs[vpc]["source"]["vpcId"]
                    source_region=vpcs[vpc]["source"]["region"]
                    vpc_cidr=vpcs[vpc]["destination"]["cidrBlock"]

    s3 = boto3.client('s3')
    
    bucket_name="ecu-protection-bucket"
    file_key = protectionTimelineId+'.json'
    
    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    file_content = response['Body'].read().decode('utf-8')
    
    subnet_route_data = json.loads(file_content)

    sts_client = boto3.client('sts')

    # Function to check if a role has access to a VPC
    def has_vpc_access(credentials, vpc_id, region):
        for assumed_role_object in credentials:
            # Create EC2 client using the assumed role
            ec2_client = boto3.client('ec2', region_name=region,
                                    aws_access_key_id=assumed_role_object['AccessKeyId'],
                                    aws_secret_access_key=assumed_role_object['SecretAccessKey'],
                                    aws_session_token=assumed_role_object['SessionToken'])
            # Check if the role has access to the specified VPC
            try:
                response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
                if response['Vpcs']:
                    print("Got the credentials!")
                    return assumed_role_object
                else:
                    return False
            except Exception as e:
                    print(f"Error: {e}")
        return False

    def assume_role_and_get_credentials(sts_client, role_arn, session_name):
        assumed_role_object = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )
        return assumed_role_object['Credentials']

    session_name = "ECUAssumeRoleSession"

    def assume_roles_and_get_credentials(sts_client, role_arns, session_name):
        credentials_list = []
        for role_arn in role_arns:
            credentials = assume_role_and_get_credentials(sts_client, role_arn, session_name)
            credentials_list.append(credentials)
        return credentials_list

    # Define role ARNs and session name
    role_arns = os.environ.get('IAM_ROLE_ARNS').split(',')
    
    # Get credentials for each role
    credentials_list = assume_roles_and_get_credentials(sts_client, role_arns, session_name)

    credentials=has_vpc_access(credentials_list, vpc_id, region)

    # Create a client for the AWS EC2 service
    ec2_client = boto3.client('ec2', region_name=region,
                            aws_access_key_id=credentials['AccessKeyId'],
                            aws_secret_access_key=credentials['SecretAccessKey'],
                            aws_session_token=credentials['SessionToken'])

    subnet_ids=[]

    # Loop through the VPCs and print their IDs
    for entry in json3:
        if "SUBNET" in entry:
            subnet_list = entry["SUBNET"]
            for subnets in subnet_list:
                for subnet in subnets:
                    region=subnets[subnet]["destination"]["region"]
                    cidr=subnets[subnet]["destination"]["cidrBlock"]
                    print(cidr)
                    if cidr in subnet_route_data:
                        subnet_id=subnets[subnet]["destination"]["subnetId"]
                        subnet_ids.append(subnet_id)

    print(subnet_ids)

    # Create a Transit Gateway VPC attachment
    response = ec2_client.create_transit_gateway_vpc_attachment(
        TransitGatewayId=transit_gateway_id,
        VpcId=vpc_id,
        SubnetIds=subnet_ids,
        Options={
            'DnsSupport': 'enable',
            'Ipv6Support': 'disable'
        }
    )

    transit_gateway_attachment_id = response['TransitGatewayVpcAttachment']['TransitGatewayAttachmentId']

    # Wait for the VPC attachment to be created
    while True:
        response = ec2_client.describe_transit_gateway_attachments(
            TransitGatewayAttachmentIds=[transit_gateway_attachment_id]
        )
        state = response['TransitGatewayAttachments'][0]['State']
        if state == 'available':
            break
        print(f"Current state: {state}. Waiting for the Transit Gateway VPC attachment to become available...")
        time.sleep(10)

    print(f"Transit Gateway VPC attachment {transit_gateway_attachment_id} is now available.")

    for subnets in subnet_ids:
        subnet_response = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Subnets']

        for subnet in subnet_response:
            if subnets == subnet['SubnetId']:
                vpc_id = subnet['VpcId']

                # Store the VPC ID, CIDR block of the subnet, and the region (zone)
                subnet_cidr = subnet['CidrBlock']

                # Get the route table associated with the subnet
                route_table_response = ec2_client.describe_route_tables(Filters=[{'Name': 'association.subnet-id', 'Values': [subnets]}])
                if 'RouteTables' in route_table_response:
                    route_table_id = route_table_response['RouteTables'][0]['RouteTableId']
                    print(f"Subnet ID: {subnet_id}")
                    print(f"Route Table ID: {route_table_id}")
                    # Add routes for each CIDR block
                    for cidr, routes in subnet_route_data.items():
                        for route in routes:
                            destination_cidr = next(iter(route))  # Get the CIDR block
                            gateway = route[destination_cidr]  # Get the gateway ID
                            
                            if 'tgw' in gateway:
                                response = ec2_client.create_route(
                                    DestinationCidrBlock=destination_cidr,
                                    RouteTableId=route_table_id,
                                    GatewayId=transit_gateway_id
                                )
                                print(f"Added route for {destination_cidr} via {transit_gateway_id}: {response}")

    # Create a client for the AWS EC2 service
    ec2_client = boto3.client('ec2')

    # Attach the Transit Gateway attachment to the Transit Gateway route
    response = ec2_client.associate_transit_gateway_route_table(
        TransitGatewayRouteTableId=transit_gateway_route_table_id,
        TransitGatewayAttachmentId=transit_gateway_attachment_id
    )
    
    # Wait until the Transit Gateway route table is associated
    while True:
        response = ec2_client.describe_transit_gateway_route_tables(TransitGatewayRouteTableIds=[transit_gateway_route_table_id])
        state = response['TransitGatewayRouteTables'][0]['State']
        if state == 'available':
            break
        print(f"Current state: {state}. Waiting for the Transit Gateway route table to become available...")
        time.sleep(10)

    print(f"Transit Gateway route table {transit_gateway_route_table_id} is now available.")

    # Add propagation entry
    response = ec2_client.enable_transit_gateway_route_table_propagation(
        TransitGatewayRouteTableId=transit_gateway_route_table_id,
        TransitGatewayAttachmentId=transit_gateway_attachment_id
    )

    # Wait until the propagation entry is enabled
    while True:
        response = ec2_client.get_transit_gateway_route_table_propagations(
            TransitGatewayRouteTableId=transit_gateway_route_table_id,
            Filters=[
                {
                    'Name': 'transit-gateway-attachment-id',
                    'Values': [transit_gateway_attachment_id]
                }
            ]
        )
        if response['TransitGatewayRouteTablePropagations'][0]['State'] == 'enabled':
            break
        print("Waiting for the propagation entry to be enabled...")
        time.sleep(10)

    print("Propagation entry is now enabled.")

    # Create a static route
    response = ec2_client.create_transit_gateway_route(
        DestinationCidrBlock=vpc_cidr,
        TransitGatewayRouteTableId=transit_gateway_route_table_id,
        TransitGatewayAttachmentId=transit_gateway_attachment_id
    )
    return '200'