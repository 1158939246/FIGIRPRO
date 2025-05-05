import csv
import os
import re
import sqlite3
import json
import textwrap

from func_timeout import func_set_timeout

from global_config import info_json_path,column_meaning_path
with open(info_json_path, 'r', encoding='utf-8') as file:
    info_json = json.load(file)
with open(column_meaning_path, 'r', encoding='utf-8', errors='replace') as f:
    column_meaning_json = json.load(f)
    path_dict = {}
    for key in column_meaning_json:
        path_dict[key.lower()] = key


@func_set_timeout(10)
def execute_sql(sqlite_path, sql_query):
    # 连接到 SQLite 数据库
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()

    try:
        # 执行 SQL 语句
        cursor.execute(sql_query)
        # 提交事务（如果是写操作）
        conn.commit()
        # 获取查询结果（如果是读操作）
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return f"An error occurred: {e}"+ type(e).__name__ + str(e)
    except Exception as e:
        print(f"An error occurred: {e}")
        return f"An error occurred: {e}" + type(e).__name__ + str(e)
    finally:
        # 关闭数据库连接
        conn.close()


@func_set_timeout(10)
def run_code_get_result(code_string):
    local_vars = {}
    try:
        # Execute the code string with local_vars as the local scope
        exec(code_string, {}, local_vars)
    except Exception as e:
        return "Exception has happened in the code,and the error Message is:"+type(e).__name__+str(e)
    # Extract the result from local_vars
    if "result" not in local_vars:
        return "Exception:The 'result' variable is not defined in the code"
    result = local_vars.get('result', None)
    return result



def getHardness(item):
    if isinstance(item,int):
        return info_json[item]["difficulty"]
    if isinstance(item, str):
        question = item
    else:
        question = item["question"]
    for entry in info_json:
        if entry["question"] == question:
            return entry["difficulty"]
    return None


def getMSchema(sqlite_path, tableNames, usedColumns=None, columnsComments=None, valueComments=None, exampleValues=None):
    import sqlite3

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()

    # Ensure all inputs are correctly structured
    usedColumns = usedColumns or [[] for _ in tableNames]
    columnsComments = columnsComments or [[] for _ in tableNames]
    valueComments = valueComments or [[] for _ in tableNames]
    exampleValues = exampleValues or [[[] for _ in range(len(usedColumns[idx]))] for idx in range(len(tableNames))]

    schema = {table: {} for table in tableNames}

    for idx, table in enumerate(tableNames):
        # Fetch columns and their types
        cursor.execute(f"PRAGMA table_info('{table}')")
        all_columns = [
            {
                'name': row[1],
                'type': row[2],
                'primary_key': bool(row[5])
            } for row in cursor.fetchall()
        ]

        # Apply usedColumns filter or use all columns, maintaining the order of usedColumns
        if idx < len(usedColumns) and usedColumns[idx]:
            filtered_columns = [col for col_name in usedColumns[idx] for col in all_columns if col['name'] == col_name]
        else:
            filtered_columns = all_columns

        schema[table]['columns'] = filtered_columns

        # Fetch foreign keys
        cursor.execute(f"PRAGMA foreign_key_list('{table}')")
        schema[table]['foreign_keys'] = [
            {
                'column': row[3],
                'ref_table': row[2],
                'ref_column': row[4]
            } for row in cursor.fetchall()
        ]

        # Fetch column comments from parameters or use defaults
        schema[table]['comments'] = {
            col['name']: (
                columnsComments[idx][col_idx] if idx < len(columnsComments) and col_idx < len(
                    columnsComments[idx]) else ''
            ) for col_idx, col in enumerate(filtered_columns)
        }

        # Fetch random examples for each column from parameters or use defaults
        schema[table]['examples'] = {
            col['name']: (
                exampleValues[idx][col_idx] if idx < len(exampleValues) and col_idx < len(exampleValues[idx]) else []
            ) for col_idx, col in enumerate(filtered_columns)
        }

        # Fetch value comments from parameters or use defaults
        schema[table]['value_comments'] = {
            col['name']: (
                valueComments[idx][col_idx] if idx < len(valueComments) and col_idx < len(valueComments[idx]) else ''
            ) for col_idx, col in enumerate(filtered_columns)
        }

    conn.close()

    # Build output
    output = []
    output.append("【Schema】")

    for table, details in schema.items():
        output.append(f"# Table: {table}")

        field_lines = []
        for column in details['columns']:
            field_line = f"({column['name']}:{column['type'].upper()}"
            if column['primary_key']:
                field_line += ", Primary Key"

            column_comment = details['comments'].get(column['name'], '').strip()
            if column_comment:
                field_line += f", ColumnComment: {column_comment}"

            value_comment = details['value_comments'].get(column['name'], '').strip()
            if value_comment:
                field_line += f", ValueComment: {value_comment}"

            examples = details['examples'].get(column['name'], [])
            if examples:
                field_line += f", Example: [{', '.join(map(str, examples))}]"

            field_line += ")"
            field_lines.append(field_line)

        output.append('[')
        output.append(',\n'.join(field_lines))
        output.append(']')

    output.append("【Foreign keys】")
    for table, details in schema.items():
        for fk in details['foreign_keys']:
            output.append(f"{table}.{fk['column']}={fk['ref_table']}.{fk['ref_column']}")

    return '\n'.join(output)

def formatOutput(result):
    if isinstance(result, int):
        return str(result)
    elif isinstance(result, str):
        if len(result) > 300:
            return f"{result[:150]}...{result[-150:]} (length: {len(result)})"
        return result
    elif isinstance(result, list):
        if len(result) > 10:
            return f"total length: {len(result)}, and the first 5 and the last 5 lines are: {formatOutput(str(result[:5]))} ... {formatOutput(result[-5:])}"
        return formatOutput(str(result))
    else:
        result = str(result)
        if len(result) > 300:
            return f"{result[:150]}...{result[-150:]} (length: {len(result)})"
        return result


def getSql(text):
    # Find all matches of SQL between triple backticks
    sql_matches = re.findall(r'```sql(.*?)```', text, re.DOTALL)
    if sql_matches:
        return sql_matches[-1].strip()  # Return the last match

    # If not found, try to extract between double backticks
    sql_match = re.search(r'```(.*?)```', text, re.DOTALL)
    if sql_match:
        return sql_match.group(1).strip()

    # If still not found, return the original string
    text = text if text.strip() else "SELECT 'Hello, World!';"

    # 对 BaseModel进行统一的格式化操作
    text = text.split(":")[-1]
    text = text.strip().split('#', 1)[0].split(';', 1)[0]
    # 判断(前是否有select
    if "select" in text.split('(')[0].lower():
        text = re.search(r"(select.*)", text, re.IGNORECASE | re.DOTALL).group(1) if re.search(r"(select.*)",
                                                                                               text,
                                                                                               re.IGNORECASE) else text

    if text.strip().lower().startswith("select"):
        return text
    else:
        return "SELECT " + text

def fillKeys(sqlite_path, tables, columns):
    """
    添加主键和外键到指定的列数组。

    :param sqlite_path: SQLite 数据库文件路径
    :param tables: 一维数组，包含表名
    :param columns: 二维数组，每个子数组对应表的列名
    :return: 更新后的列数组
    """
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()

    for idx, table in enumerate(tables):
        # 获取主键
        cursor.execute(f"PRAGMA table_info('{table}')")
        primary_keys = [row[1] for row in cursor.fetchall() if row[5] == 1]  # 主键标识在第6列 (索引为5)

        # 获取外键
        cursor.execute(f"PRAGMA foreign_key_list('{table}')")
        foreign_keys = cursor.fetchall()  # 外键包含参考表名和列名

        # 添加主键到列
        for key in primary_keys:
            if key not in columns[idx]:
                columns[idx].append(key)

        # 添加外键到列
        for fk in foreign_keys:
            fk_column = fk[3]  # 当前表的外键列
            ref_table = fk[2]  # 引用的表名
            ref_column = fk[4]  # 引用的列名

            # 在当前表添加外键列
            if fk_column not in columns[idx]:
                columns[idx].append(fk_column)

            # 在引用的表中添加被引用的列
            if ref_table in tables:
                ref_table_idx = tables.index(ref_table)
                if ref_column not in columns[ref_table_idx]:
                    columns[ref_table_idx].append(ref_column)

    conn.close()
    return columns

def printDict(output, dict):
    with open(output, 'w', encoding='utf-8') as file:
        for key, value in dict.items():
            file.write(f"{key}======\n{value}\n")


def getBirdComment(db_id, table_name, column_name,db_base_dir=None):
    key = f"{db_id}|{table_name}|{column_name}"
    if key in path_dict:
        key = path_dict[key]
    if key in column_meaning_json:
        return column_meaning_json[key],""

    if db_base_dir is None:
        csv_path = f"database/{db_id}/database_description/{table_name}.csv"
    else:
        csv_path = f"{db_base_dir}/{db_id}/database_description/{table_name}.csv"
    if not os.path.exists(csv_path):
        return "", ""
    with open(csv_path, 'r', encoding='utf-8', errors='replace') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if row[0].strip() == column_name:
                col3_value = row[2].strip() if len(row) > 2 else ""
                col5_value = row[4].strip() if len(row) > 4 else ""
                return col3_value, col5_value
    return "", ""

def getBirdExapleValues(db_id, table_name, column_name,db_base_dir=None):
    if db_base_dir is None:
        sqlite_path = f"database/{db_id}/{db_id}.sqlite"
    # 从sqlite中获取3个不同的值 返回一个数组
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT \"{column_name}\" FROM \"{table_name}\" LIMIT 3")
    all_values = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Limit string length to first and last 10 characters with "..." in between
    def limit_string_length(value):
        if isinstance(value, str) and len(value) > 20:
            return value[:10] + "..." + value[-10:]
        return value

    return [limit_string_length(value) for value in all_values]

def formatCsvPath(db_id, tableNames):
    result = ""
    for table_name in tableNames:
        file_path = "database/csv/" + db_id + "/" + table_name.lower() + ".csv"
        result += f"\n {table_name}.csv path:{file_path}\n"
    return result

def getCode(text):
    # 使用正则表达式提取 ```python 和 ``` 之间的内容
    code_match = re.search(r'(```python\s*.*?\s*```)', text, re.DOTALL)
    code_match = code_match.group(1) if code_match else ""
    code_match = code_match.replace('```python\n', '').replace('```', '')
    if code_match:
        return textwrap.dedent(code_match).strip()
    return ""