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
from typing import Literal, TypedDict,Sequence,Annotated,Optional,Union
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph,END,START
from langchain_openai import AzureOpenAIEmbeddings,AzureChatOpenAI
from langchain_core.tools import InjectedToolCallId, tool
from pydantic import BaseModel
from langgraph.types import Command 
from langgraph.prebuilt import ToolNode
import dateparser
from datetime import datetime

load_dotenv()

model=AzureChatOpenAI(
    model=os.getenv("AZURE_OPENAI_MODEL_NAME"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
)

embeddings=AzureOpenAIEmbeddings(
    model=os.getenv("AZURE_OPENAI_MODEL_NAME1"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME1")
)

url = os.getenv("supabase_url")
key = os.getenv('supabase_key')
supabase :Client =create_client(url,key)

class AgentState(TypedDict,total=False):
    messages:Annotated[Sequence[BaseMessage],add_messages]
    chat_history:list[BaseMessage]
    destination:str
    specific_destination:str
    selected_hotel_name:str
    selected_hotel_id:int #new
    selected_hotel_location:str
    selected_room_name:str #new
    num_children:Union[int,str]
    num_adults:Union[int,str]
    budget:Union[int,str]
    check_in_date: str
    check_out_date: str
    hotel_list:list[int]
    room_list:list[int] #new
    show_hotel_list:bool
    show_room_list:bool #new
    step:str 
    follow_up:list[str] #follow up questions

detail_gatherer_template = f"""
Your job is to get detailed information from a user about the location they want to visit as well as call the 'update_state' tool and set the 'show_hotel_list' to 'FALSE'.

Always collect all the following information from them:

- Where they want to go, the 'Destination' (e.g., country, state, or city)
- The specific location in the destination, the 'specific_destination' (e.g., specific neighborhood, landmark, or resort)
- The number of children, 'num_children'
- The number of adults, 'num_adults'
- Their budget for the trip, 'budget'
- Their 'check_in_date' 
- Their 'check_out_date' 

** always ask one question at a time 

Ask the above details one by one, and if they are not sure about specific destination, you can update the state with unknown, dont ask them again.

** If the user is not sure about any of the above details and you have already asked them about it when calling the 'update_tool' update that parameter with 'to-be-decided'
** Dont update any state with the number 0 instead put the string 'zero'.
** Once all required details are gathered, do not say 'Thank you' or ask for confirmation. Immediately proceed to the next step/tool.
If the user provides all or part of this information in one attempt (e.g., "We want to go to Los Angeles, USA with 2 adults and 1 child, our budget is $1500, check-in on July 5, check-out on July 10"), you should decode and extract these details clearly.
** Always call the 'update_state' tool and change the show_hotel_list's state to 'FALSE'.
If you are not able to discern any of this information, ask them to clarify politely. Do not attempt to wildly guess missing details.
** Always answer in natural language no technical terms
** Always call the follow up tool after every human input to generate follow up questions.
** If the user gives a relative date like "next Thursday", use the `parse_date` tool. If it fails to parse, ask them again for a valid calendar date.

Once you have gathered **all** of the required information, call the relevant tool with the structured data you have extracted.
"""

@tool 
def parse_date(
    date_input:Union[int,str]=None,
    field:str=None,
    reference_date:str=None,
    tool_call_id:Annotated[str,InjectedToolCallId]=None
):
    """
    Converts the natural language date expressions (like 'tomorrow', 'next Friday') into a proper YYYY-MM-DD format.
    Input: date_input:The date given by the user, field:The state to update the converted date_input into 
    Output: Confirmation message that the state has been updated.
    """

    base=datetime.now()
    if reference_date:
        try:
            base=datetime.strptime(reference_date, "%Y-%m-%d")
        except Exception:
            pass

    
    parsed=dateparser.parse(str(date_input),
                            settings={
                                'PREFER_DATES_FROM':'future',
                                'RELATIVE_BASE':base
                            })

    if parsed is None:
        return Command(update={
            'messages':[
                ToolMessage(content=f"Could not parse date input: '{date_input}'. Please try again.",
                    tool_call_id=tool_call_id)
            ]
        })
    formatted = parsed.strftime("%Y-%m-%d")
    return Command(update={
        "messages": [
            ToolMessage(    
                content=f"Parsed date: {formatted}",
                tool_call_id=tool_call_id,
            )
        ],
        field: formatted,
    })

@tool
def update_state(
    destination:str=None,
    specific_destination:str=None,
    selected_hotel_name:str=None,
    selected_hotel_location:str=None,
    selected_room_name:str=None,
    num_children:Union[int,str]=None,
    num_adults:Union[int,str]=None,
    budget:Union[int,str]=None,
    # check_in_date:str=None,
    # check_out_date:str=None,
    hotel_list:list[int]=None,
    show_hotel_list:bool=None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> str:
    """
    Update the booking state with provided details.
    Use this tool to store or update information such as destination, specific_destination and any relevant information as the user provides them.
    Inputs: Any combination of booking-related fields (destination, specific_destination etc).
    Output: Confirmation message that the state has been updated.
    """
    updated_state = {}
    if destination is not None:
        updated_state['destination']=destination
    if budget is not None:
        updated_state["budget"] = budget
    if specific_destination is not None:
        updated_state['specific_destination']=specific_destination
    if num_children is not None:
        updated_state['num_children']=num_children
    if num_adults is not None:
        updated_state['num_adults']=num_adults
    # if check_in_date is not None:
    #     updated_state['check_in_date']=check_in_date
    # if check_out_date is not None:
    #     updated_state['check_out_date']=check_out_date
    if selected_hotel_name is not None:
        updated_state['selected_hotel_name']=selected_hotel_name
    if selected_hotel_location is not None:
        updated_state['selected_hotel_location']=selected_hotel_location
    if hotel_list is not None:
        updated_state['hotel_list']=hotel_list
    if show_hotel_list is not None:
        updated_state['show_hotel_list']=show_hotel_list
    if selected_room_name is not None:
        updated_state['selected_hotel_name']=selected_room_name

    
    updated_state["messages"] = [
        ToolMessage(
            content="State updated successfully.",
            tool_call_id=tool_call_id,
        )
    ]

    return Command(update=updated_state)


def follow_up(state:AgentState):
    """
    Creates follow up question for the user based on the last message
    input=the complete chat history including the last user message which is the state 'messages'
    output=Confirmation message that the state has been updated.
    """
    updated_state={}
    follow_up_prompt="""
    You are an AI assistant helping a user with hotel booking.

Based on the chat history and the user's last message, generate 3 concise follow-up answers or questions or statements that the user might answer next or might naturally ask or want to consider next regarding their hotel booking.

- If the last user message is a greeting or unrelated to hotel booking, respond with a friendly greeting.
- While gathering the user's information, try to guess the answer that might be next. 
** Make it 3-5 words max.
- Do NOT generate questions that the assistant should be asking to gather missing info.
- Instead, generate questions or comments that the user might ask about hotel options, booking details, or related concerns.
- Ensure the questions are relevant to the user's current booking context.
- Avoid repeating information already given in the chat history."""
    messages=[SystemMessage(content=follow_up_prompt)]+(messages or [])
    response=model.invoke(messages)
    print(f"Response from follow_up tool: {response}")
    if isinstance(response,AIMessage):
        follow_up_questions=response.content.split('\n')
        follow_up_questions=[q.strip() for q in follow_up_questions if q.strip()]
        updated_state['follow_up']=follow_up_questions
    return {**state, **updated_state}

d_tools=ToolNode([update_state,parse_date])

def check_primary_details(state:AgentState)->bool:
    """
    Check if all the primary details are present in the state. """
    required_fields = [
        state.get("destination"),
        # state.get("specific_destination"),
        state.get("num_children"),
        state.get("num_adults"),
        state.get("budget"),
        state.get("check_in_date"),
        state.get("check_out_date")
    ]
    if all(required_fields):
        return True
    return False

def call_details_gatherer(state:AgentState):
    if check_primary_details(state):
        return state
    
    messages=state['messages']
    d_model=model.bind_tools([update_state,parse_date])
    messages=[SystemMessage(content=detail_gatherer_template)]+messages
    response=d_model.invoke(messages)
    # messages=state['messages']+[response]
    # follow_up(messages)
    # location=state.get('destination','')
    # spec_loc=state.get('specific_destination')
    # print(f'destination:{location} specific location:{spec_loc}')
    return {"messages": state["messages"] + [response]}

def should_continue_details_gatherer(state:AgentState):
    """check if the last message contains tool calls"""
    messages=state['messages']
    last_message=messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return 'd_tools'
    return END

def details_gatherer_supervisor(state:AgentState):
    
    if check_primary_details(state):
        # Do NOT generate any AI message, just proceed to hotel search
        return 'HotelSearchRAGAgent'
    else:
        return END

Details_gatherer=(StateGraph(AgentState)
                  .add_node('details_gatherer',call_details_gatherer)
                  .add_node('d_tools',d_tools)

                  .add_conditional_edges('details_gatherer',
                                         should_continue_details_gatherer,
                                         [
                                             'd_tools',END
                                         ]
                                         )
                  .add_edge('d_tools','details_gatherer')
                  .add_edge(START,'details_gatherer')
                  ).compile()

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
    "List ALL hotels according to the user's preferences "
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

rag_tools=[
    Tool(
        name="HotelsInfoTool",
        func=lambda input,**kwargs:rag_chain.invoke({"input":input,"chat_history":kwargs.get("chat_history",[])}),
        description="useful for when you need to retrieve hotels or answer the questions or information about the hotels",
        args_schema=ToolInput

    ),update_state
]

def should_continue_rag_agent(state:AgentState):
    """Check if the last message contains tool calls"""
    result=state['messages'][-1]
    return hasattr(result,'tool_calls') and len(result.tool_calls)>0

system_prompt = """
    You are an intelligent hotel booking assistant. 
    Use the HotelsInfoTool to list all the best hotels according to the users preferences around 4-5 hotels or more(Dont give unrelated hotels). Near by ones to the location is also good.
    Always pass the user’s query as the 'input' argument when calling this tool.
    ** After/while giving the hotels option's to the user call the 'update_state' tool and update the hotel_list state with the supabase hotel_id's of the retrived hotels.
    ** only when displaying the hotel's list call the 'update_state' tool and put show_hotel_list to true otherwise false.
    ** Just display all the hotel relevant name as the 'AI Message'.No asterisk.
    ** Always call the follow up tool after every human input to generate follow up questions.
    """

chat_history=ConversationBufferWindowMemory(memory_key="chat_history",k=10,return_messages=True)

initial_message=("You are an AI assistant that can provide helpful answers using avaliable tools")

chat_history.chat_memory.add_message(SystemMessage(content=initial_message))

def call_rag_agent(state: AgentState) -> AgentState:
    messages = list(state['messages'])
    chat_hist = state.get("chat_history", [])
    rag_model=model.bind_tools(rag_tools)
    messages = [SystemMessage(content=system_prompt)] + chat_hist + messages
    message = rag_model.invoke(messages)
    return {**state,'messages': [message], 'chat_history': chat_hist}

rag_tool_node = ToolNode(tools=rag_tools)

Rag_agent=(StateGraph(AgentState)
           .add_node('Rag_agent',call_rag_agent)
           .add_node('rag_tools',rag_tool_node)
           .add_node('follow_up', follow_up)
           .add_conditional_edges(
               'Rag_agent',
               should_continue_rag_agent,
               {
                   True:'rag_tools',
                   False:END
               }
           )

           .add_edge('rag_tools','Rag_agent')
           .set_entry_point('Rag_agent')
           ).compile()

Booking_agent_prompt="""
    You are an Helpful assistant who helps to confirm and book the hotels.

    Always collect all the following information from them:

    - The room type they want.

    ** After the user selects the hotel, call the 'update_state' tool and update the selected_hotel_name state with the hotel name and the selected_hotel_location with the hotel's location.
    ** After the user selects the room type, call the 'update_state' tool and update the selected_room_name state.
    ** Always call the 'update_state' tool and change the show_hotel_list's state to 'FALSE'.
    ** Always call the follow up tool after every human input to generate follow up questions.
    Say thank you for the selection or something like that.
"""


Booking_agent_tools=ToolNode([update_state])

def call_booking_agent(state:AgentState):
    messages=state['messages']
    messages=[SystemMessage(content=Booking_agent_prompt)]+messages
    Booking_Agent_model=model.bind_tools([update_state])
    response=Booking_Agent_model.invoke(messages)
    return {**state,'messages':state['messages']+[response]}

def should_continue_booking_agent(state:AgentState):
    """Ckeck if contains tool_calls"""
    last_messages=state['messages'][-1]
    if last_messages.tool_calls:
        return 'Booking_agent_tools'
    return END

BookingAgent=(StateGraph(AgentState)
              .add_node('BookingAgent',call_booking_agent)
              .add_node('Booking_agent_tools',Booking_agent_tools)
              .add_conditional_edges('BookingAgent',
                                     should_continue_booking_agent,
                                     {
                                        'Booking_agent_tools',
                                        END
                                     })
              .add_edge('Booking_agent_tools','BookingAgent')
              .set_entry_point('BookingAgent')
              ).compile()

class Router(BaseModel):
    next:Literal[
        "DetailsGatherer",
        "HotelSearchRAGAgent",
        "BookingAgent"
    ]
    reasoning:str

router_prompt = """You are an intelligent routing assistant for a hotel booking AI system.

Given the conversation so far, your job is to determine which of the following actions the system should take next:

- 'DetailsGatherer': Collect the destination,specific destination,budget, number of children, number of adults, check in date, check out date.
 (call the next agent only after all the above infromation has been specified.)
- 'HotelSearchRAGAgent': If the user has provided sufficient details to search for hotels and wants recommendations.
- 'BookingAgent': If the user has chosen a hotel and is ready to proceed with booking and for selecting the room type.

Respond with ONLY the name of the action to take next, and nothing else.
"""

def ai_router(state:AgentState):
    messages=state['messages']
    message=model.with_structured_output(Router).invoke(messages)
    required_fields = [
        state.get("destination"),
        # state.get("specific_destination"),
        state.get("num_children"),
        state.get("num_adults"),
        state.get("budget"),
        state.get("check_in_date"),
        state.get("check_out_date")
    ]

    # missing_fields=[field for field in required_fields if not field ]

    if not all(required_fields):
        return {"step": "DetailsGatherer"}
    else:
        return {'step':message.next}

    # if len(missing_fields)>1:
    #     return {"step": "DetailsGatherer"}
    # else:
    #     return {'step':message.next}

def router_supervisor(state:AgentState):
    return state['step']



graph=StateGraph(AgentState)
graph.add_node('DetailsGatherer',Details_gatherer)
graph.add_node("HotelSearchRAGAgent", Rag_agent)
graph.add_node("BookingAgent", BookingAgent)
graph.add_node('Router',ai_router)
graph.add_node('follow_up', follow_up)

graph.add_conditional_edges('Router',
                            router_supervisor,
                            {
                                "DetailsGatherer": "DetailsGatherer",
                                "HotelSearchRAGAgent": "HotelSearchRAGAgent",
                                "BookingAgent": "BookingAgent",
                            })

graph.add_conditional_edges('DetailsGatherer',
                            details_gatherer_supervisor,
                            {
                                "HotelSearchRAGAgent": "HotelSearchRAGAgent",
                                'follow_up':'follow_up',
                            })

graph.add_edge(START,'Router')
# graph.add_edge("DetailsGatherer", "HotelSearchRAGAgent")
# graph.add_edge("DetailsGatherer", END)
graph.add_edge("HotelSearchRAGAgent", END)
graph.add_edge("BookingAgent", END)

agent=graph.compile()



# def running_agent():
#     chat_history = []  # optional: preserve history over turns
#     print("Type 'exit' or 'quit' to end the chat.")

#     while True:
#         user_input = input("\nYou: ")
#         if user_input.lower() in ['exit', 'quit']:
#             break

#         user_msg = HumanMessage(content=user_input)
#         chat_history.append(user_msg)

#         response = agent.invoke({
#             "messages": chat_history,
#             "chat_history": chat_history,
#         })

#         # Update history with latest AI message
#         ai_msg = response["messages"][-1]
#         chat_history.append(ai_msg)

#         print(f"\nAI: {ai_msg.content}")

# running_agent()
