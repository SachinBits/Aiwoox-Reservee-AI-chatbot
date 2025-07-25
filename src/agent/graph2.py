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
from dotenv import load_dotenv
from langsmith import traceable
from typing import TypedDict,Sequence,Annotated
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph,END,START
from langchain_openai import AzureOpenAIEmbeddings,AzureChatOpenAI
from langchain.tools import tool,Tool

load_dotenv()


url = "https://plxwdqmqiaxrdwlcmzdc.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBseHdkcW1xaWF4cmR3bGNtemRjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTI3NjU5NCwiZXhwIjoyMDY2ODUyNTk0fQ.KqZeNmr6pMrUNzPxlLwgDqABBOjBq9bB6IgL3CEFZLw"

supabase :Client =create_client(url,key)

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


class AgentState(TypedDict):
    messages:Annotated[Sequence[BaseMessage],add_messages]
    room_type:str
    amenities:list[str]
    
## For asking details
def ask_room_type(state:AgentState)->AgentState:
    """This asks the user for their preference of their room type"""
    print(f"AI: Welcome! To help you find the perfect stay, could you please let me know your preferred type of room?")
    user_input=input("You: ")
    state['room_type']=user_input
    return state



def ask_amenities(state:AgentState)->AgentState:
    """This asks the user for their preference of amenities"""
    print(f"AI: Thank you! Could you also please specify any amenities or inclusions you would like during your stay?")
    user_input=input("You: ")
    state['amenities']=[a.strip() for a in user_input.split(',')]
    return state

@tool 
def generate_sentence(room_type:str,amenities:list[str]):
    """Creates a query with respect to the room_types and amenities provided"""
    system_message="Create a query with respect to the room_types and amenities provided which will be the most efficient in finding the hotels with the required specifics and only return the final senetence no additional words"
    message_query=SystemMessage(content=system_message)
    query=HumanMessage(content=f'Room_type:{room_type}, Amenities:{amenities}')
    message=[message_query]+[query]
    query=model.invoke(message)
    return query


tools_1=[generate_sentence]

model.bind_tools(tools_1)

def model_call(state: AgentState) -> AgentState:
    system_prompt = SystemMessage(content="You are my assistant who helps me to create a sentence in natural language " \
    "that will help query hotels based on the given room type and amenities.")
    
    query_input = f"Room type: {state['room_type']}, Amenities: {', '.join(state['amenities'])}"
    user_message = HumanMessage(content=query_input)
    
    response = model.invoke([system_prompt, user_message])
    
    return {
        "messages": state["messages"] + [user_message, response],
        "room_type": state["room_type"],
        "amenities": state["amenities"]
    }

tools_dict_model = {our_tool.name: our_tool for our_tool in tools_1}

def take_action_model(state:AgentState)->AgentState:
    """Execute tool calls from llm's response"""

    tool_calls=state['messages'][-1].tool_calls
    results=[]
    for t in tool_calls:
        print(f"Calling Tool: {t['name']} ")

        if not t['name'] in tools_dict_model :
            print(f"\nTool: {t['name']} does not exist.")
            result = "Incorrect Tool Name, Please Retry and Select tool from List of Available tools."
        
        else:
            result = tools_dict_model[t['name']].invoke(t['args'].get('query', ''))
            print(f"Result length: {len(str(result))}")
            

        
        results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=str(result)))

    print("Tools Execution Complete. Back to the model!")
    return {
        'messages': state["messages"] + results,
        'room_type': state["room_type"],
        'amenities': state["amenities"]
    }

def should_continue(state:AgentState):
    """Check if the last message contains tool calls"""
    result=state['messages'][-1]
    return hasattr(result,'tool_calls') and len(result.tool_calls)>0

system_prompt = """
You are an intelligent hotel booking assistant. 
Use the HotelsInfoTool to answer questions about hotels.
Always pass the user’s query as the 'input' argument when calling this tool.
"""


## rag

tools_rag=[
    Tool(
        name="HotelsInfoTool",
        func=lambda input,**kwargs:rag_chain.invoke({"input":input,"chat_history":kwargs.get("chat_history",[])}),
        description="useful for when you need to answer the questions or information about the hotels",
        args_schema=ToolInput

    )
]

rag_model=model.bind_tools(tools_rag)

tools_dict_rag = {our_tool.name: our_tool for our_tool in tools_rag}

def call_llm_rag(state: AgentState) -> AgentState:
    """Function to call the LLM with the current state."""
    messages = list(state['messages'])
    messages = [SystemMessage(content=system_prompt)] + state['messages']+messages
    message = rag_model.invoke(messages)
    return {'messages': [message],'chat_history': state['messages']}

def take_action_rag(state: AgentState) -> AgentState:
    """Execute tool calls from the LLM's response."""

    tool_calls = state['messages'][-1].tool_calls
    results = []
    for t in tool_calls:
        tool_name = t['name']
        tool_input = t['args'].get('input', 'No input provided')  
        print(f"Calling Tool: {tool_name} with input: {tool_input}")
        
        if not t['name'] in tools_dict_rag: 
            print(f"\nTool: {t['name']} does not exist.")
            raw_result = "Incorrect Tool Name, Please Retry and Select tool from List of Available tools."
        
        else:
            raw_result = tools_dict_rag[tool_name].invoke(
            tool_input,
            chat_history=state['messages']
            )
            print(f"\n\n{raw_result}")
            print(f"Result length: {len(str(raw_result))}")
            
            if isinstance(raw_result, dict):
                answer = raw_result.get("answer", str(raw_result))
            else:
                answer = str(raw_result)
        
        results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=answer))

    print("Tools Execution Complete. Back to the model!")
    return {'messages':state['messages'] +results,'chat_history': state['messages']}


graph=StateGraph(AgentState)

graph.add_node("ask room",ask_room_type)
graph.add_node("ask amenities",ask_amenities)
graph.add_node("model",model_call)
graph.add_node('sentence creator',take_action_model)
graph.add_node('rag_model',call_llm_rag)
graph.add_node('hotel_agent',take_action_rag)

graph.add_edge('ask room','ask amenities')
graph.add_edge('ask amenities','model')
graph.add_edge('model','sentence creator')
graph.add_edge('sentence creator','rag_model')
graph.add_edge('rag_model','hotel_agent')
graph.add_conditional_edges(
    "rag_model",
    should_continue,
    {True: "hotel_agent", False: END}
)


graph.set_entry_point('ask room')

app=graph.compile()


# def run_agent():
#     print("Welcome to the Hotel Assistant!")
#     initial_state = {
#         "messages": [],
#         "room_type": "",
#         "amenities": [],     
#     }

#     result = app.invoke(initial_state)
#     final_msg = result["messages"][-1].content.strip() if result["messages"] else "No final message"
#     print("\n=== FINAL OUTPUT ===")
#     print(final_msg)

# run_agent()

