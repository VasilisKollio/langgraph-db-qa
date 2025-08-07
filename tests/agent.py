import sqlite3
import getpass
import os
import ast
import re

from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.prompts import ChatPromptTemplate
from typing_extensions import TypedDict, Annotated
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser
from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain.agents.agent_toolkits import create_retriever_tool
from typing import Optional


class State(TypedDict):
    question: str
    query: Optional[str]
    result: Optional[str]
    answer: str
    feedback: Optional[str]

db = SQLDatabase.from_uri(  
    "sqlite:///C:/Users/AI_PC2/Desktop/Lang_sql_test/Chinook_Sqlite.sqlite")

llm = ChatOllama(model="codegemma:latest", temperature=0.5)

toolkit = SQLDatabaseToolkit(db=db, llm=llm)

tools = toolkit.get_tools()

tools

prompt_text = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {dialect} query to run,
then look at the results of the query and return the answer. Unless the user
specifies a specific number of examples they wish to obtain, always limit your
query to at most {top_k} results.

You can order the results by a relevant column to return the most interesting
examples in the database. Never query for all the columns from a specific table,
only ask for the relevant columns given the question.

You MUST double check your query before executing it. If you get an error while
executing a query, rewrite the query and try again.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the
database.

To start you should ALWAYS look at the tables in the database to see what you
can query. Do NOT skip this step.

Then you should query the schema of the most relevant tables.
""".format(
    dialect="SQLite",
    top_k=5,
)


prompt_template = ChatPromptTemplate.from_template(prompt_text)
system_message = prompt_template.format(dialect="SQLite", top_k=5)

# Create agent
# agent_executor = create_react_agent(llm, toolkit.get_tools(), prompt=system_message)

# Query agent
'''
example_query = "Which country's customers spent the most?"

events = agent_executor.stream(
    {"messages": [("user", example_query)]},
    stream_mode="values",
)
for event in events:
    event["messages"][-1].pretty_print()
'''
'''
question = "Describe the PlaylistTrack table" 
# Won't understand the question when i write "playlisttrack" instead of "PlaylistTrack",
# need to write the name excactly as in the table 
# "table_names {'playlisttrack'} not found in database"

for step in agent_executor.stream(
    {"messages": [{"role": "user", "content": question}]},
    stream_mode="values",
):
    step["messages"][-1].pretty_print()

'''
###



###
'''
# In order to filter columns that contain proper nouns such as addresses, song names or artists, 
# we first need to double-check the spelling in order to filter the data correctly.

# We can achieve this by creating a vector store with all the distinct proper nouns that exist in the database.
# We can then have the agent query that vector store each time the user includes a proper noun in their question, 
# to find the correct spelling for that word. In this way, the agent can make sure it understands which entity the user
# is referring to before building the target query.
'''

# First we need the unique values for each entity we want, 
# for which we define a function that parses the result into a list of elements:

def query_as_list(db, query):
    res = db.run(query)
    res = [el for sub in ast.literal_eval(res) for el in sub if el]
    res = [re.sub(r"\b\d+\b", "", string).strip() for string in res]
    return list(set(res))

artists = query_as_list(db, "SELECT Name FROM Artist")
albums = query_as_list(db, "SELECT Title FROM Album")

# Select an embeddings model and vector store 

embeddings = OllamaEmbeddings(model="llama3")

vector_store = Chroma(
    collection_name="example_collection",
    embedding_function=embeddings,
    persist_directory="./chroma_langchain_db",  # Where to save data locally, remove if not necessary
)

# We can now construct a retrieval tool that can search over relevant proper nouns in the database

_ = vector_store.add_texts(artists + albums)
retriever = vector_store.as_retriever(search_kwargs={"k": 5})
description = (
    "Use to look up values to filter on. Input is an approximate spelling "
    "of the proper noun, output is valid proper nouns. Use the noun most "
    "similar to the search."
)
retriever_tool = create_retriever_tool(
    retriever,
    name="search_proper_nouns",
    description=description,
)

# print(retriever_tool.invoke("Alice Chains"))

# Add to system message
suffix = (
    "If you need to filter on a proper noun like a Name, you must ALWAYS first look up "
    "the filter value using the 'search_proper_nouns' tool! Do not try to "
    "guess at the proper name - use this function to find similar ones."
)

system = f"{system_message}\n\n{suffix}"

tools.append(retriever_tool)

agent = create_react_agent(llm, tools, prompt=system)

# Initialize SQLDatabaseChain for count/fact queries
db_chain = SQLDatabaseChain.from_llm(
    llm=llm,
    db=db,
    verbose=True,
    # return_intermediate_steps = True is optional if you need SQL/logs
)

"""

# Now we can ask questions about the database using the agent:
question = "How many Albums does Alice in Chains have?"

for step in agent.stream(
    {"messages": [{"role": "user", "content": question}]},
    stream_mode="values",
):
    step["messages"][-1].pretty_print()
    
"""
def run_agent(state: State) -> dict:
    question = state["question"].strip()
    print("\n-- Dispatching via SQLDatabaseChain or Agent --")

    try:
        if question.lower().startswith("how many"):
            # Use SQLDatabaseChain for count queries
            result = db_chain.invoke({"question": question})
            if isinstance(result, dict) and "answer" in result:
                answer = result["answer"]
                query = result.get("intermediate_steps", [{}])[-1].get("sql_cmd", "")
            else:
                answer = str(result)
                query = ""
            
            return {
                "question": question,
                "answer": answer, 
                "query": query, 
                "result": str(result),
                "feedback": None
            }

        # Otherwise use the agent
        response = None
        for step in agent.stream(
            {"messages": [{"role": "user", "content": question}]},
            stream_mode="values",
        ):
            response = step["messages"][-1]

        answer = response.content if hasattr(response, "content") else str(response)
        
        return {
            "question": question,
            "answer": answer,
            "query": "Generated by agent",  # 
            "result": "Agent response",     # 
            "feedback": None
        }
        
    except Exception as e:
        return {
            "question": question,
            "answer": f"Error occurred: {str(e)}",
            "query": "",
            "result": "",
            "feedback": None
        }

###
def get_feedback(state: State) -> dict:
    feedback = input("Do you approve this answer? (yes/no) or type a suggestion: ").strip()
    
    return {
        "question": state["question"],
        "query": state.get("query", ""),
        "result": state.get("result", ""),
        "answer": state["answer"],
        "feedback": "approved" if feedback.lower() == "yes" else feedback
    }

# Get feedback from user
def get_feedback(state: State) -> dict:
    
    feedback = input("Do you approve this answer? (yes/no) or type a suggestion: ").strip()

    if feedback.lower() == "yes":
        return {"feedback": "approved"}
    return {"feedback": feedback}

# Routing logic
def feedback_check(state: State) -> str:
    return END if state["feedback"] == "approved" else "run_agent"

# LangGraph Workflow
graph_builder = StateGraph(State)

graph_builder.add_node("run_agent", run_agent)
graph_builder.add_node("get_feedback", get_feedback)

graph_builder.set_entry_point("run_agent")
graph_builder.add_edge("run_agent", "get_feedback")
graph_builder.add_conditional_edges("get_feedback", feedback_check)

graph = graph_builder.compile()

# Interactive SQL Agent with Feedback
def interactive_sql_loop():
    print("Interactive SQL Agent with Feedback. Type 'exit' to quit.")

    while True:
        question = input("\nEnter your question: ").strip()
        if question.lower() == "exit":
            break

        state = {
            "question": question,
            "query": None,
            "result": None, 
            "answer": "",
            "feedback": None
        }

        for event in graph.stream(state, stream_mode="values"):
            answer = event.get("answer")
            if answer:
                print(f"\nAnswer:\n{answer}")

        print("\n--- End of response ---")

if __name__ == "__main__":
    interactive_sql_loop()


