import argparse
import json
import subprocess
import sys
import uuid

def check_gcp_environment():
    """
    Validates the local Google Cloud environment before executing any API calls.
    
    Verifies that the user has an active, authenticated account and that a 
    target project ID has been explicitly configured in the gcloud CLI. If 
    either check fails, the script terminates immediately to prevent rolling failures.

    Inputs:
        None

    Returns:
        None

    Raises:
        SystemExit: If no active authenticated account is found or if no target 
                    GCP project is currently set.
    """
    print("=== Validating Google Cloud Environment ===")
    
    # Check active documentation
    auth_cmd = ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"]
    auth_result = subprocess.run(auth_cmd, capture_output=True, text=True)
    
    if not auth_result.stdout.strip():
        sys.exit("[FATAL] No active Google Cloud account found. Please run 'gcloud auth login' first.")
    
    active_account = auth_result.stdout.strip()
    print(f"[*] Authenticated as: {active_account}")

    # Check active project
    project_cmd = ["gcloud", "config", "get-value", "project"]
    project_result = subprocess.run(project_cmd, capture_output=True, text=True)
    
    if not project_result.stdout.strip():
        sys.exit("[FATAL] No active GCP project set. Please run 'gcloud config set project YOUR_PROJECT_ID'.")
        
    active_project = project_result.stdout.strip()
    print(f"[*] Target Project: {active_project}\n")


def run_bulk_create(machine_type, region, count, allow_split, run_id):
    """
    Attempts to provision Spot instances in bulk within a single targeted region.

    Wraps the 'gcloud compute instances bulk create' API. It dynamically sets the 
    minimum acceptable count based on whether the user allows cross-region splitting. 
    If the creation fails, it parses the standard error output to classify the failure 
    mode (e.g., Quota versus Capacity Stockout).

    Inputs:
        machine_type (str): The Google Compute Engine machine type configuration (e.g., 'g2-standard-4').
        region (str): The specific GCP region to target for creation (e.g., 'us-central1').
        count (int): The total number of instances requested for this specific region attempt.
        allow_split (bool): Flag indicating if partial fulfillment is allowed. If False, the API 
                            must provision all requested instances in a single zone or fail.
        run_id (str): A unique string identifier appended to instance names to prevent naming collisions.

    Returns:
        tuple: (provisioned_count, error_type)
            - provisioned_count (int): The exact number of VMs successfully created (0 if failed).
            - error_type (str or None): String mapping the failure ('QUOTA', 'STOCKOUT', 'UNKNOWN') 
                                        if provisioned_count is 0, otherwise None.
    """
    name_pattern = f"spot-{machine_type.split('-')[0]}-{run_id}-#"
    min_count = 1 if allow_split else count
    
    cmd = [
        "gcloud", "compute", "instances", "bulk", "create",
        f"--name-pattern={name_pattern}",
        f"--region={region}",
        f"--count={count}",
        f"--min-count={min_count}",
        f"--machine-type={machine_type}",
        "--provisioning-model=SPOT",
        "--format=json"
    ]
    
    print(f"[*] Searching {region} for {count} nodes (min acceptable: {min_count})...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            created_vms = json.loads(result.stdout)
            provisioned_count = len(created_vms)
            print(f"[SUCCESS] Provisioned {provisioned_count} instances in {region}.")
            return provisioned_count, None
        except json.JSONDecodeError:
            print("[WARNING] Succeeded but failed to parse gcloud output.")
            return count, None
    else:
        error_msg = result.stderr.lower()
        if "quota_exceeded" in error_msg or "quota" in error_msg:
            return 0, "QUOTA"
        elif "zone_resource_pool_exhausted" in error_msg or "not have enough resources" in error_msg:
            return 0, "STOCKOUT"
        else:
            print(f"[ERROR] Unexpected failure in {region}:\n{result.stderr}")
            return 0, "UNKNOWN"


def main():
    """
    Main orchestration function for the Spot Hunter workflow.

    Parses CLI arguments, initiates the environment validation check, pulls the region 
    priority matrices from 'config.json', and executes a serial search loop across 
    eligible regions until the targeted node count is achieved or all regions are exhausted.

    Inputs:
        None (Reads arguments from sys.argv)

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="Hunt for Spot GPUs across GCP regions.")
    parser.add_argument("--machine-type", required=True, help="e.g., g2-standard-4")
    parser.add_argument("--count", type=int, required=True, help="Number of instances needed")
    parser.add_argument("--allow-split", action="store_true", help="Allow fulfilling the total count across multiple regions")
    args = parser.parse_args()

    # Pre-flight environment check
    check_gcp_environment()

    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        sys.exit("[FATAL] config.json not found.")

    if args.machine_type not in config:
        sys.exit(f"[FATAL] Machine type {args.machine_type} not found in config.json")

    regions = config[args.machine_type].get("regions", [])
    remaining_count = args.count
    run_id = str(uuid.uuid4())[:6]
    
    print(f"=== Starting Spot Hunt for {args.count}x {args.machine_type} ===")
    
    for region in regions:
        if remaining_count <= 0:
            break
            
        provisioned, error_type = run_bulk_create(args.machine_type, region, remaining_count, args.allow_split, run_id)
        
        if provisioned > 0:
            remaining_count -= provisioned
            if remaining_count > 0:
                print(f"[*] Still need {remaining_count} more instances. Moving to next region...")
        else:
            if error_type == "QUOTA":
                print(f"[SKIP] Quota exceeded in {region}. Moving to next region.")
            elif error_type == "STOCKOUT":
                print(f"[SKIP] Out of capacity in {region}. Moving to next region.")

    if remaining_count == 0:
        print("\n=== COMPLETE: All instances successfully provisioned! ===")
    else:
        print(f"\n=== INCOMPLETE: Exhausted all configured regions. Still missing {remaining_count} instances. ===")


if __name__ == "__main__":
    main()
