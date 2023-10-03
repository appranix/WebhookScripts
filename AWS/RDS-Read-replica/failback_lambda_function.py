import boto3
import os
import time

#values
aws_access_key_id =''
aws_secret_access_key =''
primary_region = 'us-west-2'
secondary_region = 'us-east-1'
zone_id = 'Z0750194GGTMP7PDAFV9'
record_name = 'db.locationapp.in'

#tagvalues
tag_key = 'action'
tag_value = 'delete'


def lambda_handler(event, context):
    delete_ec2 = boto3.resource('ec2', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=primary_region)
    delete_rds = boto3.client('rds', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=primary_region)
    rds = boto3.client('rds', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=secondary_region)
    create_rds = boto3.client('rds', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=primary_region)
    cname_update = boto3.client('route53', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)



# Delete EC2 instances
    instances = delete_ec2.instances.filter(
        Filters=[{'Name': f'tag:{tag_key}', 'Values': [tag_value]}]
    )
    for instance in instances:
        instance.terminate()
    print(f'Deleting instance')

# Delete RDS instances
    response = delete_rds.describe_db_instances()
    for db_instance in response['DBInstances']:
        arn = db_instance['DBInstanceArn']
        tags = delete_rds.list_tags_for_resource(ResourceName=arn)['TagList']
        for tag in tags:
            if tag['Key'] == tag_key and tag['Value'] == tag_value:
                delete_rds.delete_db_instance(
                    DBInstanceIdentifier=db_instance['DBInstanceIdentifier'],
                    SkipFinalSnapshot=True
                )
                print(f'Deleting RDS instance: {db_instance["DBInstanceIdentifier"]}')

    response = rds.describe_db_instances()
    for db_instance in response['DBInstances']:
        arn = db_instance['DBInstanceArn']
        tags = rds.list_tags_for_resource(ResourceName=arn)['TagList']
        for tag in tags:
            if tag['Key'] == tag_key and tag['Value'] == tag_value:
                
                print(f'Promoting RDS instance: {db_instance["DBInstanceIdentifier"]}')
#promoting the read replica to primary
                rds.promote_read_replica(
                    DBInstanceIdentifier=db_instance['DBInstanceIdentifier'],
                    BackupRetentionPeriod=1,
                )
                print('Waiting for 8 minute after promoting the read replica...')
                time.sleep(480)
#creating read replica for promoted rds         
                create_rds.create_db_instance_read_replica(
                    DBInstanceIdentifier=db_instance['DBInstanceIdentifier'] + '-replica',
                    SourceDBInstanceIdentifier=db_instance['DBInstanceArn'],
                    SourceRegion=primary_region,
                    DBSubnetGroupName='locationapp-subnetgroup',
                    KmsKeyId='arn:aws:kms:us-west-2:981120068431:key/b64c8f43-ecea-4038-bee0-269069d3edc5',
                    Tags=[
                    { 
                    'Key': tag_key,
                    'Value': tag_value
                    }
                    ]
                )
                print(f'Creating read replica for: {db_instance["DBInstanceIdentifier"]}')
#cname update in route53
                cname = db_instance['Endpoint']['Address']
                print(cname)
                response = cname_update.list_resource_record_sets(
                HostedZoneId=zone_id,
                StartRecordName=record_name,
                StartRecordType='CNAME',
                MaxItems='1')
                
                record = response['ResourceRecordSets'][0]
                if record['Name'] == record_name or record['Type'] == 'CNAME':
                    record['ResourceRecords'][0]['Value'] = cname
    
                    response = cname_update.change_resource_record_sets(
                        HostedZoneId=zone_id,
                        ChangeBatch={
                            'Changes': [
                                {
                                    'Action': 'UPSERT',
                                    'ResourceRecordSet': record
                                }
                            ]
                        }
                    )
