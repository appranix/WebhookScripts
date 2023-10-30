import boto3
import json

def lambda_handler(event, context):
    # Initialize boto3 clients
    iam = boto3.client('iam', region_name='us-west-2')
    s3 = boto3.client('s3', region_name='us-west-2')

    # List of IAM role names to back up
    role_names = ['testing1-iam','testing-iam']

    # S3 bucket information
    bucket_name = 'iam-role-backup-01'
    folder_name = 'timeline-id'

    for role_name in role_names:
        # Get the IAM role
        role = iam.get_role(RoleName=role_name)

        # Convert CreateDate to string
        role['Role']['CreateDate'] = role['Role']['CreateDate'].isoformat()

        # Get the attached policies
        attached_policies = iam.list_attached_role_policies(RoleName=role_name)

        # Save the role and policies in a dict
        backup = {
            'Role': role['Role'],
            'AttachedPolicies': attached_policies['AttachedPolicies']
        }

        # Backup custom managed policies
        for policy in attached_policies['AttachedPolicies']:
            if not policy['PolicyArn'].startswith('arn:aws:iam::aws:policy/'):
                # Get the policy version
                policy_version = iam.get_policy_version(
                    PolicyArn=policy['PolicyArn'],
                    VersionId=iam.get_policy(PolicyArn=policy['PolicyArn'])['Policy']['DefaultVersionId']
                )

                # Backup the policy document
                backup[policy['PolicyName']] = policy_version['PolicyVersion']['Document']

                print(f"Backed up {policy['PolicyName']}")

        # Create the S3 object key with the folder structure and role name as the file name
        s3_key = f'{folder_name}/{role_name}.json'

        # Write the dict to a JSON file
        with open('/tmp/' + role_name + '.json', 'w') as f:
            json.dump(backup, f)
        
        # Upload the JSON file to S3 with the specified folder structure and role name as the file name
        s3.upload_file('/tmp/' + role_name + '.json', bucket_name, s3_key)

