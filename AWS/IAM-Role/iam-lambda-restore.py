import boto3
import json

def lambda_handler(event, context):
    # Initialize boto3 clients
    iam = boto3.client('iam', region_name='us-west-2')
    s3 = boto3.client('s3', region_name='us-west-2')

    # S3 bucket information
    bucket_name = 'iam-role-backup-01'
    folder_name = 'timeline-id'

    # Get the list of objects in the S3 bucket
    objects = s3.list_objects(Bucket=bucket_name, Prefix=folder_name)

    for obj in objects['Contents']:
        # Get the role name from the S3 object key
        role_name = obj['Key'].split('/')[-1].replace('.json', '')

        # Download the JSON file from S3
        s3.download_file(bucket_name, obj['Key'], '/tmp/' + role_name + '.json')

        # Load the dict from the JSON file
        with open('/tmp/' + role_name + '.json', 'r') as f:
            backup = json.load(f)

        # Create a new IAM role with the prefix 'new'
        new_role_name = 'new' + role_name
        iam.create_role(
            RoleName=new_role_name,
            AssumeRolePolicyDocument=json.dumps(backup['Role']['AssumeRolePolicyDocument'])
        )

        # Restore custom managed policies and attach AWS managed policies
        for policy in backup['AttachedPolicies']:
            if policy['PolicyArn'].startswith('arn:aws:iam::aws:policy/'):
                # Attach the AWS managed policy to the new IAM role
                iam.attach_role_policy(
                    RoleName=new_role_name,
                    PolicyArn=policy['PolicyArn']
                )
                print(f"Attached {policy['PolicyName']} to {new_role_name}")
            else:
                # Get the policy version and create a new custom policy with the prefix 'new'
                policy_version = iam.get_policy_version(
                    PolicyArn=policy['PolicyArn'],
                    VersionId=iam.get_policy(PolicyArn=policy['PolicyArn'])['Policy']['DefaultVersionId']
                )
                new_policy_name = 'new-' + policy['PolicyName']
                try:
                    iam.create_policy(
                        PolicyName=new_policy_name,
                        PolicyDocument=json.dumps(policy_version['PolicyVersion']['Document'])
                    )
                    print(f"Restored {policy['PolicyName']} to {new_policy_name}")
                except iam.exceptions.EntityAlreadyExistsException:
                    print(f"{new_policy_name} already exists, skipping creation")

                # Attach the new custom policy to the new IAM role
                iam.attach_role_policy(
                    RoleName=new_role_name,
                    PolicyArn=f'arn:aws:iam::{backup["Role"]["Arn"].split(":")[4]}:policy/{new_policy_name}'
                )
                print(f"Attached {new_policy_name} to {new_role_name}")
