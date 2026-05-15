import requests

BASE_URL = "http://localhost:8000/workflow/monitor/workflows"

# List of workflow IDs to delete
workflow_ids = [
"CALL-20260512-F916B5-202605151351",
"CALL-20260512-F916B5-202605151527",
"CALL-20260512-F916B5-202605151626",
"CALL-20260512-F916B5-202605151745",
"CALL-20260512-F916B5-202605151359",
"CALL-20260512-F916B5-202605151353",
"CALL-20260512-F916B5-202605151446",
"CALL-20260512-F916B5-202605151600",
"CALL-20260512-F916B5-202605151630",
"CALL-20260512-F916B5-202605151752",
"CALL-20260512-F916B5-202605151524",
"CALL-20260512-F916B5-202605151347",
"CALL-20260512-F916B5-202605151641",
"CALL-20260512-F916B5-202605151529",
"CALL-20260512-F916B5-202605151611"
]

headers = {
    "accept": "application/json"
}

def delete_workflow(workflow_id: str):
    url = f"{BASE_URL}/{workflow_id}"
    try:
        response = requests.delete(url, headers=headers)

        if response.status_code == 200:
            print(f"✅ Deleted: {workflow_id}")
            print(response.json())
        else:
            print(f"❌ Failed: {workflow_id} | Status: {response.status_code}")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error deleting {workflow_id}: {e}")

def main():
    for wf_id in workflow_ids:
        delete_workflow(wf_id)

if __name__ == "__main__":
    main()