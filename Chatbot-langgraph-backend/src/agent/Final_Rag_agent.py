from supabase import create_client,Client
from langchain.prompts import MessagesPlaceholder,ChatPromptTemplate
from langchain_core.messages import SystemMessage,HumanMessage,AIMessage,BaseMessage,ToolMessage
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.runnables import Runnable
from langchain.agents import Tool,create_react_agent,AgentExecutor
from langchain.memory import ConversationBufferMemory,ConversationBufferWindowMemory
import os
from langchain.tools import tool
from dotenv import load_dotenv
from langsmith import traceable
from typing import TypedDict,Sequence,Annotated
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph,END,START
from langgraph.prebuilt import ToolNode
 
load_dotenv()


url = "https://plxwdqmqiaxrdwlcmzdc.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseHdkcW1xaWF4cmR3bGNtemRjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTI3NjU5NCwiZXhwIjoyMDY2ODUyNTk0fQ.KqZeNmr6pMrUNzPxlLwgDqABBOjBq9bB6IgL3CEFZLw"

supabase :Client =create_client(url,key)

from langchain_openai import AzureOpenAIEmbeddings,AzureChatOpenAI


embeddings=AzureOpenAIEmbeddings(
    model=os.getenv("AZURE_OPENAI_MODEL_NAME1"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME1")
)

model=AzureChatOpenAI(
    model=os.getenv("AZURE_OPENAI_MODEL_NAME"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)


@traceable(name="SupabaseRetriever")
class SupabaseRetriever(Runnable):
    def invoke(self, input, config=None):
    # Accept input as string or dict
        if isinstance(input, dict):
            query = input.get("input") or input.get("query") or ""
        else:
            query = input  # input is string

        embedding = embeddings.embed_query(query)
        response = supabase.rpc(
            "match_documents",
            {
                "query_embedding": embedding,
                "match_threshold": 0,
                "match_count": 10
            }
        ).execute()
        

        if response.data:
            for doc in response.data:
                print(doc)
            return [Document(page_content=doc) for doc in response.data]
        return []




contextualize_system_prompt=(
    "Given a chat history and the lastest user question "
	    "which might reference context in the chat history "
	    "formulae a standalone question which can be understood "
	    "without the chat history. Do NOT answer the question, just "
   "reformulate it if needed and otherwise return it as is"
)

qa_system_prompt = (
    "You are a superb assistant who can help customers to book hotels according to their preferences. "
    "Use the following pieces of retrieved context to answer the question. "
    "List ALL hotels with cabin room types explicitly if the user requests cabin hotels. "
    "If you don't know, say so politely. Be concise but ensure you include all requested hotels."
    "\n\n{context}"
)

messages=[
    ("system",contextualize_system_prompt),
    MessagesPlaceholder("chat_history"),
    ("user","{input}")
]

messages1=[
    ("system",qa_system_prompt),
    MessagesPlaceholder("chat_history"),
    ("user","{input}")
]

contextualize_system_template=ChatPromptTemplate.from_messages(messages)
qa_system_template=ChatPromptTemplate.from_messages(messages1)

question_answer_chain=create_stuff_documents_chain(model,qa_system_template)

retriever=SupabaseRetriever()

history_aware_retriever=create_history_aware_retriever(model,retriever,contextualize_system_template)
rag_chain=create_retrieval_chain(history_aware_retriever,question_answer_chain)


from langchain import hub
react_docstore_prompt=hub.pull("hwchase17/react")

from pydantic import BaseModel

class ToolInput(BaseModel):
    input: str

tools=[
    Tool(
        name="HotelsInfoTool",
        func=lambda input,**kwargs:rag_chain.invoke({"input":input,"chat_history":kwargs.get("chat_history",[])}),
        description="useful for when you need to answer the questions or information about the hotels",
        args_schema=ToolInput

    )
]


model=model.bind_tools(tools)

class AgentState(TypedDict,total=False):
    messages:Annotated[Sequence[BaseMessage],add_messages]
    chat_history:list[BaseMessage]


def should_continue(state:AgentState):
    """Check if the last message contains tool calls"""
    result=state['messages'][-1]
    return hasattr(result,'tool_calls') and len(result.tool_calls)>0

system_prompt = """
You are an intelligent hotel booking assistant. 
Your job is to get information from a user about the location they want to visit

You should get the following information from them:

- Where they want to go, the 'Destination'
- the specific location in the destination, the '   specific_destination'

If you are not able to discern this info, ask them to clarify! Do not attempt to wildly guess.

After you are able to discern all the information, call the relevant tool

Use the HotelsInfoTool to answer questions about hotels.
Always pass the user’s query as the 'input' argument when calling this tool.
"""


tools_dict = {our_tool.name: our_tool for our_tool in tools}

chat_history=ConversationBufferWindowMemory(memory_key="chat_history",k=10,return_messages=True)


initial_message=("You are an AI assistant that can provide helpful answers using avaliable tools")

chat_history.chat_memory.add_message(SystemMessage(content=initial_message))




def call_llm(state: AgentState) -> AgentState:
    messages = list(state['messages'])
    chat_hist = state.get("chat_history", [])
    messages = [SystemMessage(content=system_prompt)] + chat_hist + messages
    message = model.invoke(messages)
    return {'messages': [message], 'chat_history': chat_hist}



def take_action(state: AgentState) -> AgentState:
    """Execute tool calls from the LLM's response."""

    tool_calls = state['messages'][-1].tool_calls
    results = []
    for t in tool_calls:
        tool_name = t['name']
        tool_input = t['args'].get('input', 'No input provided')  # FIXED LINE
        print(f"Calling Tool: {tool_name} with input: {tool_input}")
        
        if not t['name'] in tools_dict: 
            print(f"\nTool: {t['name']} does not exist.")
            result = "Incorrect Tool Name, Please Retry and Select tool from List of Available tools."
        
        else:
            result = tools_dict[tool_name].invoke(
            tool_input,
            chat_history=state['chat_history']
            )
            print(f"Result length: {len(str(result))}")
            

        # Appends the Tool Message
        results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=str(result)))

    print("Tools Execution Complete. Back to the model!")
    return {'messages': results,'chat_history': state['chat_history']}

graph=StateGraph(AgentState)

graph.add_node("llm",call_llm)

graph.add_node("hotel_agent",take_action)

graph.add_conditional_edges(
    "llm",
    should_continue,
    {True: "hotel_agent", False: END}
)

graph.add_edge("hotel_agent", "llm")
graph.set_entry_point("llm")

rag_agent = graph.compile()



def running_agent():
    print("\n=== RAG AGENT===")
    
    while True:
        user_input = input("\nWhat is your question: ")
        if user_input.lower() in ['exit', 'quit']:
            break

        chat_history.chat_memory.add_message(HumanMessage(content=user_input))
            
        messages = [HumanMessage(content=user_input)]

        response = rag_agent.invoke({"messages": messages,"chat_history": chat_history.load_memory_variables({}).get("chat_history", [])})
        chat_history.chat_memory.add_message(response["messages"][-1])
        
        print("\n=== ANSWER ===")
        print(response['messages'][-1].content)


running_agent()
