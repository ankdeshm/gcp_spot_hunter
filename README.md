# GCP Spot GPU Hunter

High-demand accelerators are frequently out of stock in specific zones. This tool automates the search for Spot capacity across multiple Google Cloud regions. It recursively checks your preferred regions and provisions the VMs as soon as it finds available capacity.

## Prerequisites: Check Your Spot Quota
Before running this tool, you must ensure you have the required **Preemptible** quota for the chips you want to use. Spot instances use Preemptible quota, not standard On-Demand quota.

1. Go to the **Google Cloud Console** > **IAM & Admin** > **Quotas & System Limits**.
2. Filter by `Quota: Preemptible`.
3. Add a second filter for your chip (e.g., `Metric: Preemptible NVIDIA L4 GPUs`).
4. Ensure your limit in your target regions is $\ge$ the number of nodes you are requesting. If it is 0, request a quota increase.

## Quick Start

1. **Clone the repository and navigate into it:**
   ```bash
   git clone https://github.com/YOUR_ORG/gcp-spot-hunter.git
   cd gcp-spot-hunter
   ```

2. **Ensure you are authenticated with Google Cloud:**
      ```bash
      gcloud auth login
      gcloud config set project YOUR_PROJECT_ID
      ```

3. **Verify or update your target regions in `config.json`:**
   The script uses this file to determine which regions to search, in order of priority.
   ```json
   {
     "g2-standard-4": {
       "regions": ["us-central1", "us-east5", "us-west1", "europe-west4"]
     }
   }


## Usage Examples
Run the spot_hunter.py script with your required parameters.

**Scenario A: Strict Single-Region Placement (Distributed Workloads)**
If you need 4 nodes, and they must be in the same zone to minimize network latency, run this. The script will only provision VMs if it can find all 4 in a single zone within a region.

```bash
python3 spot_hunter.py --machine-type=g2-standard-4 --count=4
```


**Scenario B: Split Across Regions (Independent Experiments)**
If you just need 4 nodes for independent experiments and you don't care if 2 are in us-central1 and 2 are in us-east5, use the --allow-split flag.

```bash
python3 spot_hunter.py --machine-type=g2-standard-4 --count=4 --allow-split
```
