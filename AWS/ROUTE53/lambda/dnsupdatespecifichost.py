import json
import boto3
from urllib.request import urlopen
import logging
import os
import time
logger = logging.getLogger()

logger.setLevel(logging.INFO)

message = "Something went wrong !!!"

# Appranix Resource Types that are supported in this script
# RESOURCE_LIST=COMPUTE,APPLICATION_LOAD_BALANCER,CLASSIC_LOAD_BALANCER,RDS_INSTANCE
aws_resource_list = os.environ.get('RESOURCE_LIST')
resouce_list = aws_resource_list.split(',')

# Appranix Resource Property that are supported in this script to be replaced with that of equivalend recovered resource 
# RESOURCE_PROPERTIES_LIST=publicIpAddress,privateIpAddress,privateDnsName,publicDnsName,dnsName,endpoint
aws_resource_properties_list = os.environ.get('RESOURCE_PROPERTIES_LIST')
resource_properties_list = aws_resource_properties_list.split(',')

# Record type that are supported in Route53, currently testing only A record and CName 
# RECORD_TYPE_LIST=A,AAAA,CNAME,MX,TXT,PTR,SRV,SPF,NAPTR,CAA,NS,DS
aws_record_type_list = os.environ.get('RECORD_TYPE_LIST')
record_type_list = aws_record_type_list.split(',')

list_of_dict_to_process = []

# TODO change this
# HOSTED_ZONE_ID=zone_id1,zone_id2
hosted_zones = os.environ.get('HOSTED_ZONE_ID')
hosted_zones_to_update = hosted_zones.split(',')

client = boto3.client('route53')

class DnsUpdateException(Exception):

    def __init__(self, message="Something went wrong!!!"):
        self.message = message
        logger.error(message)
        super().__init__(self.message)


def update_alias_records(hosted_id, record_name, record_type, new_value, targetZoneId):
    response = client.change_resource_record_sets(
        HostedZoneId=hosted_id,
        ChangeBatch={
            "Comment": "DNS Alias Record Updated Programatically",
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": record_name,
                        "Type": record_type,
                        "AliasTarget":{
                            'HostedZoneId': targetZoneId,
                            'DNSName': new_value + ".",
                            'EvaluateTargetHealth': True
                        },
                    }
                },
            ]
        }
    )
    logger.info(f"Updating the DNS alias record for {record_name} with {new_value}.")


def getLoadBalancerDNS(recvLbDNSName, recvRegion):
    # Get the load balancer DNS name from recovered region
    arn_list = os.environ.get("RESOURCE_ACCOUNT_IAM_ROLE_ARN")
    role_arn_list = arn_list.split(',')
    for role_arn in role_arn_list:
        # logging.info(role_arn)
        logging.info(f"Finding LoadBalancers DNS Name in the {recvRegion} using the ARN {role_arn}")
        sts_client = boto3.client('sts', region_name=recvRegion)
        response = sts_client.assume_role(RoleArn=role_arn, RoleSessionName='AssumedSession')
        credentials = response['Credentials']
        # Initialize the ELB client
        elb_client = boto3.client('elbv2', aws_access_key_id=credentials['AccessKeyId'],
                             aws_secret_access_key=credentials['SecretAccessKey'],
                             aws_session_token=credentials['SessionToken'], region_name=recvRegion)
    
        response = elb_client.describe_load_balancers()
        logging.info(response['LoadBalancers'])
        for lb in response['LoadBalancers']:
            lb_name = lb['LoadBalancerName']
            lb_dns = lb['DNSName']
            if lb_dns == recvLbDNSName:
                logging.info(f"Matched Load Balancer Name: {lb_name} and its DNS Endpoint: {lb_dns}\nCanonicalHostedZoneId: {lb['CanonicalHostedZoneId']}")
                return lb['CanonicalHostedZoneId']
        logging.info(f"No LoadBalancers found with specified name in the account with role {role_arn}")

def findRecoveredResourceAlias(recoveredDNSNameToCheckAlias):
    logging.info(f"Finding DNS Alias for {recoveredDNSNameToCheckAlias}")
    recoveryRegion = recoveredDNSNameToCheckAlias.split('.')[1]
    logging.info(f"Recovery Region: {recoveryRegion}")

    recvCanonicalId = getLoadBalancerDNS(recoveredDNSNameToCheckAlias, recoveryRegion)
    if recvCanonicalId is not None:
        logging.info(f"Found Canonical Hosted Zone ID is {recvCanonicalId}")
        return recvCanonicalId
    else:
        logger.error(f"Failed as the return value of the CanonicalHostedZoneId is NONE")
        return {
            "statusCode": 505,
            "body": json.dumps({"Status": "Failed","Message": "Returned CanonicalHostedZoneId is NONE"})
        }


#Update with new records for the hosted_id mapping to the record_name
def updateRecordSetwithNewValue(hosted_id, record_name, record_type, new_value):
    response = client.change_resource_record_sets(
        HostedZoneId=hosted_id,
        ChangeBatch={
            "Comment": "DNS Record Updated Programatically",
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": record_name,
                        "Type": record_type,
                        "TTL": 180,
                        "ResourceRecords": [
                            {
                                "Value": new_value
                            },
                        ],
                    }
                },
            ]
        }
    )
    logger.info(f"Updating the DNS record for {record_name} with {new_value}")


#Find and replace all the records where source matches
def find_and_replace_all_records(findsource, replacetarget):
    logging.info("Finding and replacing all the record from the list")
    hosted_zones = hosted_zones_to_update
    for zone in hosted_zones:
        logger.info(f"Hosted Zone = {zone}")
        #List all the record set in the Hostedzone
        resource_record_sets = client.list_resource_record_sets(HostedZoneId = zone)
        if len(resource_record_sets) == 0:
            logger.info("There are no resource record sets found")
            continue
        for recordset in resource_record_sets['ResourceRecordSets']:
            for recordtype in record_type_list:
                if recordset['Type'] == recordtype:
                    logger.debug(f"Found a {recordtype} Record set")
                    if 'ResourceRecords' in recordset:
                        for resourcerecord in recordset['ResourceRecords']:
                            if resourcerecord['Value'] == findsource:
                                logger.info(f"Updating the record for {recordset}")
                                updateRecordSetwithNewValue(zone, recordset['Name'], recordtype, replacetarget)
                    if 'AliasTarget' in recordset:
                        for resourcerecord in recordset['AliasTarget']:
                            if recordset['AliasTarget']["DNSName"] == str(findsource + ".") or recordset['AliasTarget']["DNSName"] == str("dualstack." + findsource + "."):
                                recoveredZoneId = findRecoveredResourceAlias(replacetarget)
                                update_alias_records(zone, recordset['Name'], recordtype, replacetarget,recoveredZoneId)


def update_records(list_of_dict_of_source_and_target_records):
    logging.info(list_of_dict_of_source_and_target_records)
    for each_item in list_of_dict_of_source_and_target_records:
        source = each_item['source_entry']
        dest = each_item['target_entry']
        logger.info(f"Source  = {source} and Target  = {dest}")
        if source is not None and dest is not None:
            find_and_replace_all_records(source, dest)
    logging.info("Updated all Route53 Records")


def add_source_target_to_process_dict(data_dict, value_type):
    for k, v in data_dict.items():
        if value_type in v['source'].keys():
            source = v['source'][value_type]
            dest = v['destination'][value_type]
            temp_dict = {"source_entry" : source, "target_entry" : dest}
            list_of_dict_to_process.append(temp_dict)

def validateEventPayload(event):
    for key in event.keys():
        if key == "body":
            logger.info("Found body parameter block")
            return json.loads(event[key])
    logger.info("Event does not has the body block")
    return event

def lambda_handler(event, context):
    try:
        logger.info(event)
        data_dictionary = validateEventPayload(event)
        if data_dictionary["recoveryStatus"] == "RECOVERY_COMPLETED":
            url = data_dictionary["resourceMapping"]["sourceRecoveryMappingPath"]
            logger.info(url)
            response = urlopen(url)
            source_recovery_resource_mapping_json = json.loads(response.read())
            logger.info(f"source_recovery_resource_mapping_json =  {source_recovery_resource_mapping_json}")
            for source_recovery_map in source_recovery_resource_mapping_json:
                logger.info(f"source_recovery_map.keys() = {source_recovery_map.keys()}")
                for resource_type in resouce_list:
                    if resource_type in source_recovery_map.keys():
                        logger.info(f"Resource Type {resource_type}")
                        all_resource_details = list(source_recovery_map.values())
                        for each_resoucetypes in all_resource_details:
                            for each_resource in each_resoucetypes:
                                logger.info(f"Each Resources {each_resource}")
                                for resource_property in resource_properties_list:
                                    logger.debug(f"Fill all {resource_property} in the process dict")
                                    add_source_target_to_process_dict(each_resource, resource_property)

            if len(list_of_dict_to_process) != 0:
                logger.debug("Processing the data to update records based on source and destination values")
                logger.info(list_of_dict_to_process)
                update_records(list_of_dict_to_process)
                return{
                    "statusCode" : 200,
                    "body" : json.dumps({"Status": "Success","Message":"Updated all Route53 Records"})
                }
            else:
                logger.error(f"Failed as there are no source and target map found")
                return {
                    "statusCode": 505,
                    "body": json.dumps({"Status": "Failed","Message": "There are no records to update"})
                }
        else:
            message = "The Recovery did not complete successfully so skipping DNS Update"
            raise DnsUpdateException(message)
    except Exception as e:
            logger.error(f"FAILED with Exception {e}")
            return {
                "statusCode": 505,
                "body": json.dumps({"Status": "Failed","Message": "Something went wrong"})
            }
