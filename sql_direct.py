import copy
import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import util  # 假设 util 包含 SQL 执行和代码执行相关函数
from LLM import chat_with_llm
from exec_eval import eval_exec_match
from global_config import info_json_tied_append_path, info_json_path, info_rsl
from parse import remove_distinct
from result_eq import resultSqlListContainCode
from ves_eval import *

with open(
        info_json_tied_append_path,
        "r") as f:
    dev_tied = json.load(f)
with open(info_json_path, "r") as f:
    dev = json.load(f)


def get_ori_sql(idx):
    for item in dev_tied:
        if idx == item["question_id"]:
            return item["SQL"]
    return dev[idx]["SQL"]


with open(
        info_rsl,
        "r") as f:
    rsl_infos = json.load(f)


def process_file(file_path, output_dir, db_base_dir, prompt, prompt_guide_sql):
    # Write to output file
    output_file = os.path.join(output_dir, os.path.basename(file_path).replace(".json", ".json"))
    output_log_file = os.path.join(output_dir, "log", os.path.basename(file_path).replace(".json", ".log"))
    # Check if the output file already exists
    if os.path.exists(output_file):
        with open(output_file) as out_f:
            output_data = json.load(out_f)
        idx = int(os.path.basename(file_path).split("_", 1)[0])
        db_id = os.path.basename(file_path).split("_", 1)[1].replace(".json", "")
        db_path = os.path.join(db_base_dir, db_id, f"{db_id}.sqlite")
        output_data["is_sql_equal"] = (
                eval_exec_match(db_path, output_data["predicted_sql"], output_data["ori_sql"], False, False,
                                False) or eval_exec_match(db_path, output_data["predicted_sql"],
                                                          output_data["ori_sql"], False, True, False)
        )
        output_data["ves_score"] = get_time_ratio(output_data["predicted_sql"], get_ori_sql(idx), db_path,
                                                  output_data["is_sql_equal"],
                                                  10)
        return {
            "file_id": os.path.basename(file_path).split("_")[0],
            "is_code_equal": output_data["is_code_equal"],
            "is_sql_equal": output_data["is_sql_equal"],
            "hardness": output_data["hardness"],
            "ves_score": output_data["ves_score"]
        }

    with open(file_path) as f:
        infojson = json.load(f)

    # Initialize variables
    index = int(os.path.basename(file_path).split("_", 1)[0])
    db_id = os.path.basename(file_path).split("_", 1)[1].replace(".json", "")
    db_path = os.path.join(db_base_dir, db_id, f"{db_id}.sqlite")
    tables = {}
    selected_example_values = {}

    # Parse input JSON
    for item in infojson:
        if item["tool_name"] == "retrieve_entity":
            selected_example_values = item.get("schema_with_examples", {})

    rsl_info = rsl_infos[index]
    used_tables = rsl_info["tables"]
    used_columns = [
        [re.search(r'`(.+?)`', column).group(1) for column in rsl_info["columns"] if column.startswith(table)] for table
        in rsl_info["tables"]]
    used_columns = util.fillKeys(db_path, used_tables, used_columns)
    tentative_schema = {}
    for table in used_tables:
        tentative_schema[table] = used_columns[used_tables.index(table)]

    # example_prompt, used_tables, used_columns = getExamples(index, db_id, db_path, used_tables, used_columns)

    # Gather comments and examples
    columns_comments = [
        [util.getBirdComment(db_id, table, column)[0] for column in columns]
        for table, columns in zip(used_tables, used_columns)
    ]
    value_comments = [
        [util.getBirdComment(db_id, table, column)[1] for column in columns]
        for table, columns in zip(used_tables, used_columns)
    ]
    example_values = [
        [selected_example_values.get(table, {}).get(column, util.getBirdExapleValues(db_id, table, column)) for column in
         columns]
        for table, columns in zip(used_tables, used_columns)
    ]

    csv_schema = util.getMSchema(db_path, used_tables, used_columns, columns_comments, value_comments, example_values)

    question = infojson[-1]["final_SQL"]["Question"]
    evidence = infojson[-1]["final_SQL"]["Evidence"]
    sql = infojson[-1]["final_SQL"]["GOLD_SQL"]

    # Chat with model for original code
    chat_copy = copy.deepcopy(prompt)
    chat_copy[1]["content"] = chat_copy[1]["content"].format(
        # examples=example_prompt,
        csv_schema=csv_schema,
        question=question,
        csv_path=util.formatCsvPath(db_id, used_tables),
        evidence=evidence,
        tentative_schema=str(tentative_schema)
    )

    code_thought,token_cost_ = chat_with_llm(chat_copy,n=1,temperature=0,max_tokens=8192)
    code_list = [util.getCode(output) for output in code_thought]
    code_result = code_list[0]

    # Execute SQL and Code
    try:
        result_sql_answer = util.execute_sql(db_path, sql)
    except BaseException as e:
        result_sql_answer = str(e)
    try:
        result_sql_answer_removeDistinct = util.execute_sql(db_path, remove_distinct(sql))
    except BaseException as e:
        result_sql_answer_removeDistinct = str(e)
    try:
        result_code_ori = util.run_code_get_result(code_result)
    except BaseException as e:
        print(str(e))
        result_code_ori = str(e)
    is_equal = resultSqlListContainCode(result_code_ori, result_sql_answer) or resultSqlListContainCode(result_code_ori,
                                                                                                        result_sql_answer_removeDistinct)

    # Generate guided SQL
    chat_copy = copy.deepcopy(prompt_guide_sql)
    chat_copy[1]["content"] = chat_copy[1]["content"].format(
        db_schema=csv_schema,
        question=question,
        evidence=evidence,
        python_code=code_result,
        # code_exe_result=formatOutput(result_code_ori)
    )
    sql_thought,token_cost_ = chat_with_llm(chat_copy,n=1,temperature=0,max_tokens=8192)
    predicted_sql = [util.getSql(output) for output in sql_thought][0]
    try:
        result_predicted_sql = util.execute_sql(db_path, predicted_sql)
    except BaseException as e:
        result_predicted_sql = str(e)
    chat_revirse_sql = [
        {
            "role": "system",
            "content": """
            You are an AI agent responsible for generating the correct SQL statements based on the following information:
- A small number of SQL Q&A pairs: used for reference and learning common query patterns.
- Database structure information: including table names, fields, relationships between tables (such as foreign keys, etc.).
- The first three rows of values in the table: sample data for understanding the content and data distribution of the table.
- User questions: queries or questions in natural language form.
- Query requirements and conditions: specific query requirements and conditions in user questions.
- Tables involved in SQL statements: tables involved in user questions.
- Auxiliary query conditions: additional query conditions that may affect the generation of SQL statements.
- Hint: Information for prompting, this message is very important.

Your main tasks are:

1. Parse user questions:
   - Use natural language processing (NLP) techniques to parse user questions and extract query requirements and conditions.

2. Refer to SQL Q&A pairs:
    - Use the provided SQL Q&A pairs as a reference to understand common query patterns and SQL statement structures.

3. Analyze database structure information:
    - Based on the database structure information, understand the fields and relationships of the table, and build the basic framework of the SQL statement.

4. Check sample data:
    - Analyze the data characteristics based on the first three rows of the table values to help determine how to construct query conditions and filter results.

5. Generate SQL statements:
    - Based on user questions, query requirements and conditions, tables involved, and auxiliary query conditions, build a complete SQL statement.

6. Verification and optimization:
    - Check whether the generated SQL statement is logical and optimize it if necessary.

### Input:
- SQL Q&A pairs: a small number of example SQL Q&A pairs.
- Database structure information: including table names, fields, relationships between tables (such as foreign keys, etc.).
- The first three rows of values in the table: sample data.
- User questions: queries or questions in natural language form.
- Query requirements and conditions: specific query requirements and conditions in user questions.
- Auxiliary query conditions: additional query conditions.
- Hint: Information for prompting, this message is very important.

### Output:
- Return the sql in ```sql ```

### Note:
- Ensure that the SQL statement accurately reflects the query requirements and conditions in the user question.
- Reasonably construct the query logic based on the database structure and sample data.
- When generating SQL statements, consider all the provided information to ensure the correctness and efficiency of the statement.
- If the SQL statement is incorrect or inefficient, make improvements. Ensure that the statement is both efficient and accurate.
- Hint: Information for prompting, this message is very important.
- In the generated SQL statement, table names and field names need to be enclosed in backquotes, such as `table_name`, `column_name`.
- In the generated SQL statement, table names and field names must be correct to ensure the correctness and efficiency of the statement.
            """
        },
        {
            "role": "user",
            "content": f"""
            database_schema:{csv_schema}
            question:{question}
            sql:{predicted_sql}
            sql_result:{result_predicted_sql}
            #The final result should not be empty,please give me the correct sql
            """
        }
    ]
    for i in range(0):
        if result_predicted_sql is None or not result_predicted_sql or "error" in result_predicted_sql:
            if i == 0:
                sql_thought,token_cost_ = chat_with_llm(chat_revirse_sql,n=1,temperature=0,max_tokens=8192)
                predicted_sql = [util.getSql(output) for output in sql_thought][0]
            else:
                chat_revirse_sql.extend([
                    {
                        "role": "assistant",
                        "content": f"```sql {predicted_sql} ```"
                    },
                    {
                        "role": "user",
                        "content": f"""
                        The result of the SQL is {util.formatOutput(result_predicted_sql)}.
                        The result should not be empty
                        The sql is not correct, please give me the correct sql
                        """
                    }
                ])
                sql_thought,token_cost_ = chat_with_llm(chat_revirse_sql,n=1,temperature=0,max_tokens=8192)
                predicted_sql = [util.getSql(output) for output in sql_thought][0]
            try:
                result_predicted_sql = util.execute_sql(db_path, predicted_sql)
            except BaseException as e:
                result_predicted_sql = str(e)
        else:
            break

    is_equal_sql = eval_exec_match(db_path, predicted_sql, sql, False, False, False) or eval_exec_match(db_path,
                                                                                                        predicted_sql,
                                                                                                        sql, False,
                                                                                                        True, False)
    ves_score = get_time_ratio(predicted_sql, sql, db_path, is_equal_sql, 10)

    # Get question hardness
    hardness = util.getHardness(question)

    # Prepare output
    # Prepare output
    output_data = {
        "evidence": evidence,
        "question": question,
        "ori_sql": sql,
        "sql_result": result_sql_answer,
        "code_result": str(result_code_ori),
        "is_code_equal": is_equal,
        "predicted_code": code_result,
        "csv_schema": csv_schema,
        "predicted_sql": predicted_sql,
        "predicted_sql_result": result_predicted_sql,
        "is_sql_equal": is_equal_sql,
        "hardness": hardness,
        "ves_score": ves_score
        # "code_thought": code_thought,
        # "sql_thought": sql_thought
    }

    util.printDict(output_log_file, output_data)

    with open(output_file, "w") as out_f:
        json.dump(output_data, out_f, indent=4)

    output_data["sql_history"] = chat_copy
    output_data["code_thought"] = code_thought
    output_data["sql_thought"] = sql_thought

    return {
        "ves_score": ves_score,
        "file_id": os.path.basename(file_path).split("_")[0],
        "is_code_equal": is_equal,
        "is_sql_equal": is_equal_sql,
        "hardness": hardness
    }


def main():
    data_dir = "data"
    output_dir = "final_direct"
    db_base_dir = "database"
    prompt = [
        {
            "role": "system",
            "content": "You are an expert in database querying and proficient in handling data stored in CSV files, treating them as database tables. The current database has been exported to corresponding CSV files. Your task is to answer user queries by writing Python code that queries these CSV files. You will be provided with examples of past queries in the database and their SQL solutions. Use the SQL logic as a reference to formulate Python code solutions for the CSV files. Focus on providing accurate and efficient Python code that directly queries the CSV files and produces the desired result."
        },
        {
            "role": "user",
            "content":
                """
        #you should answer what csv file to use and what columns to use,and what messages you will answer before you write the code.When answering, carefully distinguish the following four elements:
        The content mentioned in the question.
        The content mentioned in the evidence.
        The description provided in the ValueComment.
        The data format provided in the Example.
    #Before merge data,use .add_prefix('tablename') to avoid the name conflicts
    #pay attention to the foreign key relationship between tables and you should merge the tables based on the foreign key relationship like sql does before you answer the question
    #you should only use the columns in the schema and the foreign key given you.Don't use other columns.
    #When filtering data, pay close attention to the format of the data in the Example field, as it represents the actual data stored in the database. Be especially cautious with strings and dates to ensure their format matches exactly, including time zones and separators.
    #Given a question and evidence, extract relevant information or make a judgment. However, please note that case sensitivity may exist between the question and evidence. To avoid issues caused by mismatched casing, always refer to the examples provided in Example: []. Use them as guidance to handle case sensitivity properly.
        #When answering the question, ensure the result directly addresses the query. Specifically:
        1. If the question asks for a field name, return the corresponding column values.
        2. If the question asks for an ID or code, ensure the correct ID or code column is used.
        3. For questions about details, identity codes, or similar information, prioritize inspecting the column names to locate the relevant field .
        4. For comparison questions, directly state the answer (e.g., the item or option) without restating the context or providing explanations.
        5. The result order should be same as the question.For example,"what is the name and id of the one with the most students registered?"you should return [(name),(id)] not [(id),(name)].
        #When you process data,you should follow
        1.Unless the question requires it, directly return the relevant data without any additional processing, such as string concatenation, truncation, etc.
        2.The result should match question,exactly without other info
        3.x between a and b means a <= x <= b, or equivalently, x >= a and x <= b.
        4.you should follow evidence

        #Please answer the following question based on the given data structure. The CSV file contains the following columns:
        {csv_schema}
        #Using python code, answer the following questions for the csv file provided above.
        #Question: {question}
        #extral knowledge:{evidence}
        #use the the following csv path to read the csv file:{csv_path}
        #Here is some tables,columns you shuold pay attention:{tentative_schema}
        # After filtering and processing the data, use `print(result)` in the end. The final answer should be stored in the variable `result`, and it should be either:
          1. An array (list).
          2. A number (integer or float).
          3. A string.
        
        #your code should be```python and ``` and the code should be valid python code
        """
        }
    ]  # Load your prompt template here
    # Here are some examples of past queries and their SQL solutions in the database:
    # {examples}

    prompt_guide_sql = [
        {
            "role": "system",
            "content": "You are an expert Python developer specializing in data analysis and database management. Your role is to assist users in transforming data queries originally written for CSV files into SQL queries for SQLite databases. Your solutions should be precise, efficient, and easy to understand."
        },
        {
            "role": "user",
            "content":
                """
        # You are tasked with helping to transform queries originally written for CSV files into equivalent queries for an SQLite database. The database structure and column names are identical to the original CSV files.
        # Your task involves:
        1. Understanding the Original Code Logic:
        * Analyze the provided Python code or logic written for CSV files.
        * Determine the user's intent and interpret the expected functionality based on the original question.
        2. Writing Precise SQL Queries:
        * Write SQL queries that replicate the same functionality or results when executed on the SQLite database.
        * pay attention to the spaces in the column name, you should use the double quotes to quote the column name
        * pay attention to the calculation of the columns ,make sure the type of the column is correct,you should use the cast function to convert the type of the column
        * Strictly follow the user's requirements:
        * Select only the columns explicitly mentioned in the user's question. Avoid including unnecessary columns or values.
        * Use SQLite functions only. For date manipulation:
                - If the date is in a SQLite-recognized format (e.g., 'YYYY-MM-DD'), use STRFTIME() (e.g., STRFTIME('%Y', SOMETIME) to extract the year)
                - For non-standard formats (e.g., 'YYYYMM'), use SUBSTR() to manually extract parts (e.g., SUBSTR(date_column, 1, 4) for year)
        3. Ensuring Accuracy of Results:
        * Validate that the logic in the query matches the user's intent.
        * Pay attention to the output to ensure it fulfills the question's requirements. Even if the original code logic is correct, ensure the result aligns precisely with the user's request.
        * Make sure the code returns results that exactly match the user’s question, without any extra columns.
        4. Optimizing for SQLite:
        * Translate Python or CSV-based operations into efficient SQL syntax suitable for SQLite.
        * Use GROUP BY, DISTINCT, and other SQLite-specific functionalities where applicable.    
        # Example Question: {question}
        #extral knowledge:{evidence}
        # Database structure: {db_schema}
        # Original Python code to solve the question: {python_code}
        # return ```sql``` and the code should be valid sql code
        """
        }
    ]  # Load guided SQL prompt template here
    # The result of the code is {code_exe_result}. You should evaluate it, and only make corrections if there is an error or if the result contains only null values.

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "log"), exist_ok=True)
    files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f[0].isdigit() and f.endswith(".json")]

    files = files
    # files =[file for file in files if "1277" in file]

    results = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [
            executor.submit(process_file, file_path, output_dir, db_base_dir, prompt, prompt_guide_sql)
            for file_path in files
        ]
        for future in futures:
            results.append(future.result())

    # Gather statistics
    stats = defaultdict(list)
    hardness_summary = defaultdict(lambda: {"total": 0, "code_correct": 0, "sql_correct": 0, "ves_scores": []})

    for result in results:
        hardness = result["hardness"]
        is_equal = result["is_code_equal"]
        is_equal_sql = result["is_sql_equal"]
        ves_score = result["ves_score"]
        file_id = result["file_id"]
        # if ves_score > 10:
        #     print(result)

        # Update basic statistics
        if is_equal and not is_equal_sql:
            stats["code_correct_sql_wrong"].append(file_id)
        if not is_equal and is_equal_sql:
            stats["sql_correct_code_wrong"].append(file_id)
        if not is_equal and not is_equal_sql:
            stats["both_wrong"].append(file_id)

        stats["hardness"].append(hardness)
        stats["total"].append(1)
        if is_equal:
            stats["code_correct"].append(1)
        if is_equal_sql:
            stats["sql_correct"].append(1)

        # Update hardness-specific statistics
        hardness_summary[hardness]["total"] += 1
        if is_equal:
            hardness_summary[hardness]["code_correct"] += 1
        if is_equal_sql:
            hardness_summary[hardness]["sql_correct"] += 1
        hardness_summary[hardness]["ves_scores"].append(ves_score)
    # Calculate code and SQL accuracy for each hardness level
    hardness_accuracy = {
        hardness: {
            "ves_score": compute_ves(summary["ves_scores"]),
            "code_accuracy": summary["code_correct"] / summary["total"],
            "sql_accuracy": summary["sql_correct"] / summary["total"],
            "total": summary["total"]
        }
        for hardness, summary in hardness_summary.items()
    }

    stats_summary = {
        "code_accuracy": sum(stats["code_correct"]) / sum(stats["total"]),
        "sql_accuracy": sum(stats["sql_correct"]) / sum(stats["total"]),
        "code_correct_sql_wrong_count": len(stats["code_correct_sql_wrong"]),
        "sql_correct_code_wrong_count": len(stats["sql_correct_code_wrong"]),
        "both_wrong_count": len(stats["both_wrong"]),
        "code_correct_sql_wrong_ids": stats["code_correct_sql_wrong"],
        "sql_correct_code_wrong_ids": stats["sql_correct_code_wrong"],
        "both_wrong_ids": stats["both_wrong"],
        "hardness_accuracy": hardness_accuracy,
        "total_ves_score": compute_ves([result["ves_score"] for result in results])
    }
    print(stats_summary)
    # Write statistics
    stats_file = os.path.join(output_dir, "statistic.json")
    with open(stats_file, "w") as stats_f:
        json.dump(stats_summary, stats_f, indent=4)


if __name__ == "__main__":
    main()
