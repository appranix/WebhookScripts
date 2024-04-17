import json
import boto3
import os

def lambda_handler(event, context):
    request_json = json.loads(event['body'])
    print(request_json)
    query_params = event['queryStringParameters']
    vpc_id=query_params['vpc_id']
    region=query_params['region']
    # bucket_name=query_params['bucket_name']
    bucket_name="ecu-protection-bucket"
    
    timeline_id=request_json['timelineItemId']
    file_name=timeline_id+'.json'
    
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
    subnet_route_data = {}

    # Find the Transit Gateway attached to the VPC
    response = ec2_client.describe_transit_gateway_vpc_attachments(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [
                    vpc_id,
                ]
            },
        ]
    )

    # Get the Transit Gateway VPC attachments
    transit_gateway_vpc_attachments = response['TransitGatewayVpcAttachments']

    subnet_route_data={}
    all_route_table_data = []  # List to store all route_table_data

    for attachment in transit_gateway_vpc_attachments:
        print(attachment['SubnetIds'])
        
        # Get the CIDR blocks of the subnets
        for subnet_id in attachment['SubnetIds']:
            subnet_response = ec2_client.describe_subnets(
                SubnetIds=[
                    subnet_id,
                ]
            )
            
            subnet_response = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Subnets']

            for subnet in subnet_response:
                if subnet_id == subnet['SubnetId']:               
                    vpc_id = subnet['VpcId']

                    # Store the VPC ID, CIDR block of the subnet, and the region (zone)
                    subnet_cidr = subnet['CidrBlock']

                    # Get the route table associated with the subnet
                    route_table_response = ec2_client.describe_route_tables(Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}])
                    # if 'RouteTables' in route_table_response:
                    #     route_table_id = route_table_response['RouteTables'][0]['RouteTableId']
                    #     print(f"Subnet ID: {subnet_id}")
                    #     print(f"Route Table ID: {route_table_id}")

                    # Iterate over each route table
                    for route_table in route_table_response['RouteTables']:                    
                        route_table_data = []
                        # Iterate over each route in the current route table
                        for route in route_table['Routes']:
                            destination = route.get('DestinationCidrBlock') or route.get('DestinationIpv6CidrBlock')
                            target = route.get('GatewayId') or route.get('NatGatewayId') or route.get('TransitGatewayId') or route.get('VpcPeeringConnectionId')
                            if destination:
                                route_table_data.append({destination: target})
                        # Only add route_table_data to subnet_route_data if it's not already in all_route_table_data
                        if True:# if route_table_data not in all_route_table_data:
                            subnet_route_data[subnet_cidr] = route_table_data
                            all_route_table_data.append(route_table_data)  # Add route_table_data to all_route_table_dataa

    print(subnet_route_data)    
    
    s3 = boto3.client('s3')
    
    s3.put_object(Body=json.dumps(subnet_route_data), Bucket=bucket_name, Key=file_name)
    print(f"Successfully uploaded {file_name} to {bucket_name}")
    
    return "200"
    