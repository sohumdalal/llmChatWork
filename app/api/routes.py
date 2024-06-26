import logging
from flask import Blueprint, request, jsonify, Response, stream_with_context, json
import requests
import sseclient
from app.services import openai_service, pinecone_service, scraping_service
from app.utils.helper_functions import chunk_text


PINECONE_INDEX_NAME = 'index237'
api_blueprint = Blueprint('api', __name__)


def add_cors_headers(response):
    logging.debug("Adding CORS headers")
    response.headers.add("Access-Control-Allow-Origin", "http://localhost:3000")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "POST,OPTIONS")
    logging.debug("CORS headers added")
    return response

# Helper function to handle CORS preflight requests
def handle_options_request():
    logging.debug("Handling OPTIONS request")
    response = jsonify(status="success")
    return add_cors_headers(response)

@api_blueprint.route('/handle-query', methods=['POST', 'OPTIONS'])
def handle_query():
    if request.method == 'OPTIONS':
        return handle_options_request()
    
    logging.debug("Handling POST /handle-query")
    question = request.json['question']
    chat_history = request.json['chatHistory']
    
    # Get the most similar chunks from Pinecone
    context_chunks = pinecone_service.get_most_similar_chunks_for_query(question, PINECONE_INDEX_NAME)
    
    # Build the payload to send to OpenAI
    headers, data = openai_service.construct_llm_payload(question, context_chunks, chat_history)

    # Send to OpenAI's LLM to generate a completion
    def generate():
        url = 'https://api.openai.com/v1/chat/completions'
        response = requests.post(url, headers=headers, data=json.dumps(data), stream=True)
        client = sseclient.SSEClient(response)
        for event in client.events():
            if event.data != '[DONE]':
                try:
                    text = json.loads(event.data)['choices'][0]['delta']['content']
                    yield text
                except Exception as e:
                    logging.error(f"Error parsing event data: {e}")
                    yield ''
    
    # Return the streamed response from the LLM to the frontend
    response = Response(stream_with_context(generate()))
    return add_cors_headers(response)

@api_blueprint.route('/embed-and-store', methods=['POST', 'OPTIONS'])
def embed_and_store():
    if request.method == 'OPTIONS':
        return handle_options_request()

    logging.debug("Handling POST /embed-and-store")
    url = request.json['url']
    url_text = scraping_service.scrape_website(url)
    chunks = chunk_text(url_text)
    pinecone_service.embed_chunks_and_upload_to_pinecone(chunks, PINECONE_INDEX_NAME)
    response_json = {
        "message": "Chunks embedded and stored successfully"
    }
    response = jsonify(response_json)
    return add_cors_headers(response)

@api_blueprint.route('/delete-index', methods=['POST', 'OPTIONS'])
def delete_index():
    if request.method == 'OPTIONS':
        return handle_options_request()

    logging.debug("Handling POST /delete-index")
    pinecone_service.delete_index(PINECONE_INDEX_NAME)
    response = jsonify({"message": f"Index {PINECONE_INDEX_NAME} deleted successfully"})
    return add_cors_headers(response)
