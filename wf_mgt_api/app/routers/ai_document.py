import os
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile , Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import shutil
import uuid
from typing import Dict, List  # Import Dict and List classes

from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter, Depends, HTTPException
from azure.storage.blob import BlobServiceClient

from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

load_dotenv()
router = APIRouter()

connect_str = os.getenv("blob_storage_connect_str")
container_name = os.getenv("container_name")
ENDPOINT = os.getenv("AZURE_DOC_INT_API_ENDPOINT")
API_KEY = os.getenv("AZURE_DOC_INT_API_KEY")

if not ENDPOINT or not API_KEY:
    raise RuntimeError("Azure Document Intelligence credentials not set")

# blob_service_client = BlobServiceClient.from_connection_string(conn_str=connect_str) # create a blob service client to interact with the storage account
# try:
#     container_client = blob_service_client.get_container_client(container=container_name) # get container client to interact with the container in which images will be stored
#     container_client.get_container_properties() # get properties of the container to force exception to be thrown if container does not exist
# except Exception as e:
#     print(e)
#     print("Creating container...")
#     container_client = blob_service_client.create_container(container_name) # create a container in the storage account if it does not exist


@router.get("/analyse_document/{full_path:path}")
async def analyse_document(input_doc_url: str):

    print(input_doc_url)
    # return {'result': input_doc_url }
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    
    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    poller = document_analysis_client.begin_analyze_document_from_url("prebuilt-idDocument", input_doc_url)
    id_documents = poller.result()
    result = { }
    for idx, id_document in enumerate(id_documents.documents):
        first_name = id_document.fields.get("FirstName").value
        last_name = id_document.fields.get("LastName").value
        document_number = id_document.fields.get("DocumentNumber").value
        dob = str(id_document.fields.get("DateOfBirth").value)
        doe = str(id_document.fields.get("DateOfExpiration").value)
        # address = id_document.fields.get("Address").value
        street_address = id_document.fields.get("Address").value.to_dict().get("street_address")
        suburb = id_document.fields.get("Address").value.to_dict().get("suburb")
        postal_code = id_document.fields.get("Address").value.to_dict().get("postal_code")
        state = id_document.fields.get("Address").value.to_dict().get("state")
        
        result = { "first_name" : first_name , "last_name" : last_name, "license_number" : document_number, 
                  "date_of_birth":dob,"date_of_expiry":doe, "street_address" : street_address,"suburb" :suburb, "postal_code" : postal_code, "state" : state}
    print(result)
    return result


@router.get("/analyse_licence/{full_path:path}")
async def analyse_licence(input_doc_url: str):

    print(input_doc_url)
    # return {'result': input_doc_url }
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    model_id = "zvicroad1"
    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    poller = document_analysis_client.begin_analyze_document_from_url(model_id=model_id,document_url = input_doc_url)
    form_recognizer_licence_result = poller.result()

    # Initialize a dictionary to store the extracted fields
    image_data = {}

    for idx, licence_document in enumerate(form_recognizer_licence_result.documents):
        print("licence_document")

        doc_data = licence_document.to_dict()

        # List of fields to extract 
        fields_to_extract = [
            'zdocumentType', 'issuedBy', 'FirstName', 'LastName', 'DocumentNumber',
            'Address', 'DateOfBirth','DateOfExpiration'
        ]

        # Loop through the fields to extract and check if they exist in the dictionary
        for field_name in fields_to_extract:
            if field_name in doc_data['fields']:
                image_data[field_name] = doc_data['fields'][field_name]['content']    

    return image_data

@router.get("/analyse_passport/{full_path:path}")
async def analyse_passport(input_doc_url: str):

    print(input_doc_url)
    # return {'result': input_doc_url }
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    model_id = "zpassport1"
    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    poller = document_analysis_client.begin_analyze_document_from_url(model_id=model_id,document_url = input_doc_url)
    form_recognizer_passport_result = poller.result()

    # Initialize a dictionary to store the extracted fields
    image_data = {}

    for idx, passport_document in enumerate(form_recognizer_passport_result.documents):
        print("passport_document")

        doc_data = passport_document.to_dict()

        # List of fields to extract
        fields_to_extract = ['DocumentName','Country', 'FirstName', 'LastName',
            'DocumentNumber', 'DateOfBirth', 'DateOfExpiration', 'DateOfIssue', 
            'Nationality', 'PlaceOfBirth', 'Sex']

        # Loop through the fields to extract and check if they exist in the dictionary
        for field_name in fields_to_extract:
            if field_name in doc_data['fields']:
                image_data[field_name] = doc_data['fields'][field_name]['content']    

    return image_data

@router.get("/analyse_electricity/{full_path:path}")
async def analyse_electricity(input_doc_url: str):

    print(input_doc_url)
    # return {'result': input_doc_url }
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    model_id = "zelectricity1"
    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    poller = document_analysis_client.begin_analyze_document_from_url(model_id=model_id,document_url = input_doc_url)
    form_recognizer_electricity_result = poller.result()

    # Initialize a dictionary to store the extracted fields
    image_data = {}

    for idx, electricity_document in enumerate(form_recognizer_electricity_result.documents):
        print("electricity_document")

        doc_data = electricity_document.to_dict()

        # List of fields to extract
        fields_to_extract = ['retailer', 'address', 'account_number', 'issue_date']

        # Loop through the fields to extract and check if they exist in the dictionary
        for field_name in fields_to_extract:
            if field_name in doc_data['fields']:
                image_data[field_name] = doc_data['fields'][field_name]['content']    

    return image_data

@router.get("/analyse_directdebit/{full_path:path}")
async def analyse_directdebit(input_doc_url: str):

    print(input_doc_url)
    # return {'result': input_doc_url }
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    model_id = "zddmodel1"
    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    poller = document_analysis_client.begin_analyze_document_from_url(model_id=model_id,document_url = input_doc_url)
    form_recognizer_directdebit_result = poller.result()

    # Initialize a dictionary to store the extracted fields
    image_data = {}

    for idx, directdebit_document in enumerate(form_recognizer_directdebit_result.documents):
        print("analyse_directdebit")

        doc_data = directdebit_document.to_dict()

        # List of fields to extract
        fields_to_extract = ['FirstName', 'LastName', 'BankName', 'BankAddress', 'AccountName', 'BSBNumber', 'AccountNumber', 'HomeAddress', 
'MobileNo', 'Email', 'SignedDate']

        # Loop through the fields to extract and check if they exist in the dictionary
        for field_name in fields_to_extract:
            if field_name in doc_data['fields']:
                image_data[field_name] = doc_data['fields'][field_name]['content']    

    return image_data

@router.get("/process_receipt/{full_path:path}")
async def process_receipt(input_doc_url: str):

    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))

    try:
        # Analyze the receipt using the pre-built "prebuilt-receipt" model from the provided URL
        poller = document_analysis_client.begin_analyze_document_from_url("prebuilt-receipt", input_doc_url)
        receipt_data = poller.result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing receipt: {str(e)}")

    # Initialize a dictionary to store the extracted fields and items
    receipt_info: Dict[str, List[Dict[str, str]]] = {'items': []}

    # Extract key information data points from the receipt
    for receipt in receipt_data.documents:
        receipt_info['merchant_name'] = receipt.fields.get("MerchantName").content
        receipt_info['MerchantAddress'] = receipt.fields.get("MerchantAddress").content
        receipt_info['transaction_date'] = receipt.fields.get("TransactionDate").content

        # Extract items information
        if receipt.fields.get("Items"):
            for idx, item in enumerate(receipt.fields.get("Items").value):
                item_info = {}
                item_info['item_description'] = item.value.get("Description").value
                if item.value.get("Quantity"):
                    item_info['item_quantity'] = item.value.get("Quantity").value
                if item.value.get("ProductCode"):
                    item_info['ProductCode'] = item.value.get("ProductCode").value
                if item.value.get("TotalPrice"):
                    item_info['item_total_price'] = item.value.get("TotalPrice").value
                receipt_info['items'].append(item_info)

        receipt_info['subtotal'] = receipt.fields.get("Subtotal").content
        if receipt.fields.get("TotalTax"):
            receipt_info['tax'] = receipt.fields.get("TotalTax").content
        if receipt.fields.get("Total"):
            receipt_info['total'] = receipt.fields.get("Total").content

    return receipt_info

@router.get("/process_invoice/{full_path:path}")
async def process_invoice(input_doc_url: str):

    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))

    try:
        # Analyze the invoice using the pre-built "prebuilt-invoice" model from the provided URL
        poller = document_analysis_client.begin_analyze_document_from_url("prebuilt-invoice", input_doc_url)
        invoices_data = poller.result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing invoice: {str(e)}")

    # Initialize a dictionary to store the extracted fields and items
    invoice_info: Dict[str, List[Dict[str, str]]] = {'items': []}

    # Extract key information data points from the invoice
    for invoice in invoices_data.documents:

        if invoice.fields.get("VendorName"):
            invoice_info['vendor_name'] = invoice.fields.get("VendorName").content
        if invoice.fields.get("VendorAddress"):
            invoice_info['vendor_address'] = invoice.fields.get("VendorAddress").content
        if invoice.fields.get("customer_name"):
            invoice_info['customer_name'] = invoice.fields.get("CustomerName").content
        invoice_info['invoice_id'] = invoice.fields.get("InvoiceId").content
        invoice_info['invoice_date'] = invoice.fields.get("InvoiceDate").content
        invoice_info['invoice_total'] = invoice.fields.get("InvoiceTotal").content
        invoice_info['purchase_order'] = invoice.fields.get("PurchaseOrder").content
        invoice_info['Customer_Name'] = invoice.fields.get("CustomerName").content
        invoice_info['billing_address'] = invoice.fields.get("BillingAddress").content
        invoice_info['shipping_address'] = invoice.fields.get("ShippingAddress").content

        # Extract items information
        if invoice.fields.get("Items"):
            for idx, item in enumerate(invoice.fields.get("Items").value):
                item_info = {}
                item_info['product_code'] = item.value.get("ProductCode").content
                item_info['item_description'] = item.value.get("Description").content
                item_info['item_quantity'] = item.value.get("Quantity").content
                item_info['UnitPrice'] = item.value.get("UnitPrice").content
                item_info['tax'] = item.value.get("Tax").content
                item_info['amount'] = item.value.get("Amount").content
                invoice_info['items'].append(item_info)

    return invoice_info

@router.get("/classify_document/{full_path:path}")
async def classify_document(input_doc_url: str):

    print(input_doc_url)
    # return {'result': input_doc_url }
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    model_id = "doc-classfication-model-v2"
    document_analysis_client = DocumentAnalysisClient(endpoint=ENDPOINT, credential=AzureKeyCredential(API_KEY))
    poller = document_analysis_client.begin_classify_document_from_url(classifier_id=model_id,document_url = input_doc_url)
    doc_classification_result = poller.result()

    # Initialize a dictionary to store the extracted fields
    image_data = {}
    confidence_pct = 0
    print("----Classified documents----")
    for doc in doc_classification_result.documents:
        print(f"Found document of type '{doc.doc_type or 'N/A'}' with a confidence of {doc.confidence}" )
        confidence_pct = 100 * doc.confidence
    if confidence_pct > 60 :
        image_data = {"doc_type" : doc.doc_type , "confidence_pct": confidence_pct }
    else:
        image_data = {"doc_type" : "invalid document" , "confidence_pct": confidence_pct }
    return image_data

@router.post("/azure-image")
async def create_upload_photo_file(file: UploadFile):

    if not file:
        return {"message": "No upload file sent"}
    else:
        # file_name = str(uuid.uuid4()) + file.filename
        filename, file_extension = os.path.splitext(file.filename)
        file_name = str(uuid.uuid4()) + file_extension
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name)

        try:
            contents = file.file.read()
            file.file.seek(0)
            blob_client.upload_blob(contents)
        except Exception:
            raise HTTPException(status_code=500, detail='Something went wrong')
        finally:
            file.file.close()


        file_url = "https://zblobarchive.blob.core.windows.net/documents/" + str(file_name)
        # return {"filename": file.filename}
        return {"fileUrl": file_url}

