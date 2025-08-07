from langchain_community.utilities import SQLDatabase

db = SQLDatabase.from_uri("sqlite:///Chinook_Sqlite.db")
print(db.dialect)
print(db.get_usable_table_names())
db.run("SELECT * FROM Artist LIMIT 10;")