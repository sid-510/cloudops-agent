"""Check that Gemini on Vertex AI works with this project's credentials."""

import os

from langchain_google_genai import ChatGoogleGenerativeAI

MODEL = os.environ.get("AGENT_MODEL", "gemini-3.7-flash")

llm = ChatGoogleGenerativeAI(
    model=MODEL,
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location="global",
    temperature=0,
)

reply = llm.invoke("In one sentence: what does an HTTP 502 status code mean?")
print(reply.text)
print(reply.usage_metadata)