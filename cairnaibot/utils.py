import io
import json
import re
import os
import tempfile
import time
import uuid
from datetime import datetime

import google.generativeai as genai
import pandas as pd
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from markdown import markdown as md
from openai import OpenAI
from tabula.io import read_pdf
from vectordb import vectordb
from cairnaibot.azure_storage_utilities import AzureStorageUtilities
from chat.models import PDFFile, Session
from chat.prompt_template import BOT_INSTRUCTIONS
from config import get_config

load_dotenv()


class Utilities:
    def __init__(self):
        self.config = get_config()
        self.azure_utils = AzureStorageUtilities()

        self.gemini_client = self.load_gemini_model()
        self.openai_client = self.load_openai_model()
        self.databricks_client = self.load_databricks_model()
        self.llama_client = self.databricks_client

    def get_session_or_404(self, session_id, request=None, user=None):
        if user:
            return get_object_or_404(Session, session_id=session_id, user=user)
        else:
            return get_object_or_404(Session, session_id=session_id, user=request.user)

    def get_admin_pdf_file(self, session_id):
        user = self.get_or_create_admin_user()
        return get_object_or_404(Session, user=user, session_id=session_id).pdf_file

    def get_or_create_admin_user(self):
        admin_username = os.getenv("ADMIN_USERNAME")
        admin_password = os.getenv("ADMIN_PASSWORD")

        admin_user, created = User.objects.get_or_create(
            username=admin_username, defaults={"password": admin_password}
        )

        return admin_user

    def check_is_admin_first_session(self):
        user = self.get_or_create_admin_user()
        session_id = "admin_session"

        return Session.objects.filter(user=user, session_id=session_id).exists()


    def sanitize_filename(self, file_name):
        """
        Sanitize the file name to avoid automatic renaming by Azure Storage.
        This function replaces spaces with underscores and removes special characters.
        
        Args:
            file_name (str): Original file name.
        
        Returns:
            str: Sanitized file name.
        """
        # Replace spaces with underscores
        file_name = file_name.replace(" ", "_")
        
        # Remove invalid characters (keep alphanumeric, underscores, dashes, and periods)
        file_name = re.sub(r"[^a-zA-Z0-9._-]", "", file_name)
        
        # Ensure the file name doesn't exceed Azure's maximum allowed length (1024 characters)
        return file_name[:1024]

    def load_gemini_model(self):
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=GOOGLE_API_KEY)

        model_config = {
            "temperature": 0.5,
            "top_p": 0.99,
            "top_k": 0,
        }

        client = genai.GenerativeModel(
            "gemini-1.5-flash-latest", generation_config=model_config
        )

        return client

    def load_openai_model(self):
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        client = OpenAI(api_key=OPENAI_API_KEY)
        return client

    def load_databricks_model(self):
        DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
        DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
        client = OpenAI(
            api_key=DATABRICKS_TOKEN,
            base_url=DATABRICKS_HOST,
        )
        return client

    def get_user_request(self, relavant_content, user_input, llm_name):
        inp = f"Content:{relavant_content}\n\nQuestion:{user_input}\n\nAnswer:"

        if llm_name == "gemini_output":
            user_request = f"USER: {inp}"
        else:
            user_request = {"role": "user", "content": inp}

        return user_request

    def get_previous_conversations(self, data, llm_name):
        if llm_name == "gemini_output":
            previous_conversations = [BOT_INSTRUCTIONS]
        else:
            previous_conversations = [{"role": "system", "content": BOT_INSTRUCTIONS}]

        for i in data:
            if llm_name in i.keys():
                user_input = i["user_input"]
                llm_output = i[llm_name]
                if llm_name == "gemini_output":
                    previous_conversations.append(f"USER: {user_input}")
                    previous_conversations.append({f"ASSISTANT : {llm_output}"})
                else:
                    previous_conversations.append(
                        {"role": "user", "content": user_input}
                    )
                    previous_conversations.append(
                        {"role": "assistant", "content": llm_output}
                    )
        return previous_conversations

    def get_llm_output(self, session, flow_index, messages, llm_name):
        llm_output = ""
        if llm_name.startswith("llama"):
            llm_params = self.config["llm_params"]["llama_params"]
            llm_params["messages"] = messages
            llm_params["stream"] = True

            chat_completion = self.llama_client.chat.completions.create(**llm_params)

            for chunk in chat_completion:
                content = chunk.choices[0].delta.content
                if content:
                    llm_output += content
                    yield f"{content}"

        if llm_name.startswith("openai"):
            llm_params = self.config["llm_params"]["openai_params"]
            llm_params["messages"] = messages
            llm_params["stream"] = True

            chat_completion = self.openai_client.chat.completions.create(**llm_params)

            for chunk in chat_completion:
                content = chunk.choices[0].delta.content
                if content:
                    llm_output += content
                    yield f"{content}"

        if llm_name.startswith("gemini"):
            chat_completion = self.gemini_client.generate_content(messages, stream=True)

            for content in chat_completion:
                if content.text:
                    llm_output += content
                    yield f"{content.text}"

        if llm_name.startswith("dbrx"):
            llm_params = self.config["llm_params"]["dbrx_params"]
            llm_params["messages"] = messages
            llm_params["stream"] = True
            chat_completion = self.databricks_client.chat.completions.create(
                **llm_params
            )

            for chunk in chat_completion:
                content = chunk.choices[0].delta.content
                if content:
                    llm_output += content
                    yield f"{content}"

        session.data[flow_index][-1][llm_name] = llm_output
        session.save()

        yield "[DONE]"

    def get_retreiver_response(self, user_id, req_session, session_id, user_input):
        # is_cloud_file = req_session.meta_data.get("is_cloud_file")

        file_names = req_session.meta_data["file_names"]

        file_results = []
        for file_name in file_names:
            result = vectordb.filter(
                metadata__user_id=user_id,
                metadata__session_id=str(session_id),
                metadata__file_name=file_name,
            ).search(user_input, k=2)
            file_results += result
        return file_results

    def parse_pdf_tables(page_binary):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(page_binary)
            temp_pdf_path = temp_pdf.name

        # Extract tables only from the provided page content
        tables = read_pdf(temp_pdf_path, pages="1", multiple_tables=True, stream=True)
        temp_table_string = ""

        for table in tables:
            for index, row in table.iterrows():
                row_json = json.dumps(row.to_dict())
                temp_table_string += f"{row_json} "

        return temp_table_string.strip()

    def add_to_session(self, session_id, documents, request, parsed_content):
        print(1)
        session = self.get_session_or_404(session_id, request)
        print(2)
        user = request.user
        print(3)

        meta_data = session.meta_data
        original_parsed_content = session.parsed_content
        print(4)

        meta_data["file_names"] = meta_data["file_names"] + [self.sanitize_filename(x.name) for x in documents]
        meta_data["number_of_files"] = meta_data["number_of_files"] + len(documents)
        # old_parsed_content+=parsed_content
        original_parsed_content = original_parsed_content+parsed_content
        print(5)

        session.meta_data = meta_data
        session.parsed_content = original_parsed_content
        session.save()
        print(6)

        for file in documents:
            print(7)
            pdf_file = PDFFile(file=file, user=user, session=session)
            pdf_file.save()
            session.pdf_files.add(pdf_file)

        print(8)
        for page_data in parsed_content:
            print(9)
            text = page_data["content"] + page_data["tables_content"]
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000, chunk_overlap=150
            )
            print(10)
            chunks = text_splitter.split_text(text)
            for chunk in chunks:
                vectordb.add_text(
                    text=chunk
                    + f"\n\nPage number: {page_data['page_number']}"
                    + f"\n\nFile Name: {page_data['file_name']}",
                    id=str(uuid.uuid4()),
                    metadata={
                        "user_id": user.id,
                        "session_id": str(session_id),
                        "page_number": page_data["page_number"],
                        "file_name": page_data["file_name"],
                    },
                )

    def create_new_session(self, session_id, documents, user, parsed_content):
        new_session = Session(
            session_id=session_id,
            user=user,
            data=[[]],
            parsed_content=parsed_content
        )


        new_session.meta_data = {
            "session_id": session_id,
            "session_name": "New Session",
            "created_date": datetime.now().strftime("%d %b %Y"),
            "file_names": [self.sanitize_filename(x.name) for x in documents],
            "number_of_files": len(list(documents)),
        }

        new_session.open_ai_conversation = None
        new_session.llama_conversation = None
        new_session.dbrx_conversation = None
        new_session.gemini_conversation = None

        new_session.save()

        for file in documents:
            pdf_file = PDFFile(file=file, user=user, session=new_session)
            pdf_file.save()
            new_session.pdf_files.add(pdf_file)

        for page_data in parsed_content:
            text = page_data["content"] + page_data["tables_content"]
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000, chunk_overlap=150
            )
            chunks = text_splitter.split_text(text)
            for chunk in chunks:
                vectordb.add_text(
                    text=chunk
                    + f"\n\nPage number: {page_data['page_number']}"
                    + f"\n\nFile Name: {page_data['file_name']}",
                    id=str(uuid.uuid4()),
                    metadata={
                        "user_id": user.id,
                        "session_id": session_id,
                        "page_number": page_data["page_number"],
                        "file_name": page_data["file_name"],
                    },
                )
    
    def create_cloud_session(self, original_session, new_session_id, new_user, original_file_names_to_keep):
        new_session = Session(
            session_id=new_session_id,
            user=new_user,
            data=original_session.data,  # Copy the original session data
            parsed_content=original_session.parsed_content,
        )
        file_names_to_keep = [f"pdfs/admin/{x}" for x in original_file_names_to_keep]

        # Filter documents based on file_names_to_keep
        relevant_documents = [
            pdf_file for pdf_file in original_session.pdf_files.all()
            if pdf_file.file.name in file_names_to_keep
        ]

        print("original_session.pdf_files", [pdf_file.file.name for pdf_file in original_session.pdf_files.all()])
        print("file_names_to_keep", file_names_to_keep)
        print("original_file_names_to_keep", original_file_names_to_keep)
        print("relevant_documents", [doc.file.name for doc in relevant_documents])

        # Update meta_data with filtered file names
        new_session.meta_data = {
            "session_id": new_session_id,
            "session_name": f"Duplicated from {original_session.session_id}",
            "created_date": datetime.now().strftime("%d %b %Y"),
            "file_names": original_file_names_to_keep,
            "number_of_files": len(original_file_names_to_keep),
        }

        # Reset conversation fields for the new session
        new_session.open_ai_conversation = None
        new_session.llama_conversation = None
        new_session.dbrx_conversation = None
        new_session.gemini_conversation = None

        new_session.save()

        # Add only the relevant PDF files to the new session
        for original_pdf in relevant_documents:
            new_pdf_file = PDFFile(file=original_pdf.file, user=new_user, session=new_session)
            new_pdf_file.save()
            new_session.pdf_files.add(new_pdf_file)

        parsed_content = original_session.parsed_content
        # print("parsed_content\n", parsed_content)
        for page_data in parsed_content:
            print(page_data["file_name"], page_data["file_name"] in original_file_names_to_keep)
            if page_data["file_name"] in original_file_names_to_keep:
                text = page_data["content"] + page_data["tables_content"]
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000, chunk_overlap=150
                )
                chunks = text_splitter.split_text(text)
                for chunk in chunks:
                    vectordb.add_text(
                        text=chunk
                        + f"\n\nPage number: {page_data['page_number']}"
                        + f"\n\nFile Name: {page_data['file_name']}",
                        id=str(uuid.uuid4()),
                        metadata={
                            "user_id": new_user.id,
                            "session_id": new_session_id,
                            "page_number": page_data["page_number"],
                            "file_name": page_data["file_name"],
                        },
                    )

        return new_session
