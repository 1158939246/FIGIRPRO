import json
import json
import os
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import util  # 假设 util 包含 SQL 执行和代码执行相关函数
from LLM import chat_with_llm
from exec_eval import eval_exec_match
from global_config import info_json_path, info_json_tied_append_path
from parse import remove_distinct
from result_eq import codeResultEq, resultSqlListContainCode, resultSqlListEqCode_codeNullFalse, \
    formatDataStr_set
from ves_eval import *

with open(info_json_tied_append_path,"r") as f:
    dev_tied=json.load(f)
with open(info_json_path,"r") as f:
    dev=json.load(f)
def get_ori_sql(idx):
    for item in dev_tied:
        if idx == item["question_id"]:
            return item["SQL"]
    return dev[idx]["SQL"]

def getMostFrequentResult(results):
    valid_results_count = [0]*len(results)
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            if codeResultEq(results[i], results[j]):
                valid_results_count[i] += 1
    max_count = max(valid_results_count)
    most_frequent_results = [results[i] for i in range(len(results)) if valid_results_count[i] == max_count]
    return most_frequent_results

def get_best_sqls(sqls, db_path, final_result):
    validSqls = []
    # Store the best SQL for each result
    best_sql_for_results = {}

    # Iterate through the SQL queries
    for sql in sqls:
        try:
            # Execute the SQL and get the result and execution time
            sql["result"], sql["time"] = execute_sql_returnResultAndTime(db_path, sql["sql"])

            # Check if the SQL result matches any of the final results
            for result_code in final_result:
                if resultSqlListContainCode(result_code, sql["result"]):
                # if resultSqlListEqCode(result_code, sql["result"]):
                    validSqls.append(sql)
                    sql_result= formatDataStr_set(sql["result"])
                    # Check if this result is already stored, or if this SQL has a shorter execution time
                    if sql_result not in best_sql_for_results or sql["time"] < best_sql_for_results[sql_result]["time"]:
                        best_sql_for_results[sql_result] = sql
                    break  # Exit the loop once a match is found for this result
        except Exception as e:
            continue
        except FunctionTimedOut:
            continue

    return list(best_sql_for_results.values())


def process_file(file_paths, output_dir, db_base_dir):
    # Write to output file
    output_file = os.path.join(output_dir, os.path.basename(file_paths[0]).replace(".json", ".json"))
    output_log_file = os.path.join(output_dir,"log", os.path.basename(file_paths[0]).replace(".json", ".log"))
    # Check if the output file already exists
    if os.path.exists(output_file) :
        with open(output_file) as out_f:
            try:
                output_data = json.load(out_f)
            except json.JSONDecodeError:
                print(f"Error reading {output_file}")
                os.remove(output_file)
        idx = int(os.path.basename(file_paths[0]).split("_", 1)[0])
        db_id = os.path.basename(file_paths[0]).split("_", 1)[1].replace(".json", "")
        db_path = os.path.join(db_base_dir, db_id, f"{db_id}.sqlite")
        output_data["predicted_sql"] = output_data["predicted_sql"].replace("|| ' ' ||", ",")
        try:
            result_sql_answer = util.execute_sql(db_path, get_ori_sql(idx))
        except BaseException as e:
            result_sql_answer = str(e)
        try:
            result_sql_answer_removeDistinct = util.execute_sql(db_path, remove_distinct(get_ori_sql(idx)))
        except BaseException as e:
            result_sql_answer_removeDistinct = str(e)
        with open(file_paths[0]) as f:
            direct_json = json.load(f)
            code_direct = direct_json["predicted_code"]
        with open(file_paths[1]) as f:
            filter_json = json.load(f)
            code_filter = filter_json["predicted_code"]
        with open(file_paths[2]) as f:
            merge_json = json.load(f)
            code_merge = merge_json["predicted_code"]
        try:
            code_direct_result = util.run_code_get_result(code_direct)
        except BaseException as e:
            code_direct_result = str(e)
        try:
            code_filter_result = util.run_code_get_result(code_filter)
        except BaseException as e:
            code_filter_result = str(e)
        try:
            code_merge_result = util.run_code_get_result(code_merge)
        except BaseException as e:
            code_merge_result = str(e)

        output_data["is_code_equal"] = (
            resultSqlListEqCode_codeNullFalse(code_direct_result,result_sql_answer)
            or resultSqlListEqCode_codeNullFalse(code_filter_result,result_sql_answer)
            or resultSqlListEqCode_codeNullFalse(code_merge_result,result_sql_answer)
    )or(
            resultSqlListEqCode_codeNullFalse(code_direct_result,result_sql_answer_removeDistinct)
            or resultSqlListEqCode_codeNullFalse(code_filter_result,result_sql_answer_removeDistinct)
            or resultSqlListEqCode_codeNullFalse(code_merge_result,result_sql_answer_removeDistinct)
    )

        output_data["hardness"] = util.getHardness(output_data["question"])
        return {
            "type": output_data["type"],
            "file_id": os.path.basename(file_paths[0]).split("_")[0],
            "is_code_equal": output_data["is_code_equal"],
            "is_sql_equal": output_data["is_sql_equal"],
            "hardness": output_data["hardness"],
            "ves_score": output_data["ves_score"]
        }

    with open(file_paths[0]) as f:
        direct_json = json.load(f)
    with open(file_paths[1]) as f:
        filter_json = json.load(f)
    with open(file_paths[2]) as f:
        merge_json = json.load(f)

    # Initialize variables
    db_id = os.path.basename(file_paths[0]).split("_", 1)[1].replace(".json", "")
    db_path = os.path.join(db_base_dir, db_id, f"{db_id}.sqlite")

    csv_schema = direct_json["csv_schema"]
    question = direct_json["question"]
    evidence = direct_json["evidence"]
    sql = direct_json["ori_sql"]
    code_direct = direct_json["predicted_code"]
    code_filter = filter_json["predicted_code"]
    code_merge = merge_json["predicted_code"]

    # Execute SQL and Code
    try:
        result_sql_answer = util.execute_sql(db_path, sql)
    except BaseException as e:
        result_sql_answer = str(e)
    try:
        result_sql_answer_removeDistinct = util.execute_sql(db_path, remove_distinct(sql))
    except BaseException as e:
        result_sql_answer_removeDistinct = str(e)
    final_result_dict = []
    try:
        if code_direct_result := util.run_code_get_result(code_direct):
            if not (isinstance(code_direct_result, str) and "Exception" in code_direct_result):
                final_result_dict.append(code_direct_result)
    except BaseException as e:
        code_direct_result = str(e)
    try:
        if code_filter_result := util.run_code_get_result(code_filter):
            if not (isinstance(code_filter_result, str) and "Exception" in code_filter_result):
                final_result_dict.append(code_filter_result)
    except BaseException as e:
        code_filter_result = str(e)
    try:
        if code_merge_result := util.run_code_get_result(code_merge):
            if not (isinstance(code_merge_result, str) and "Exception" in code_merge_result):
                final_result_dict.append(code_merge_result)
    except BaseException as e:
        code_merge_result = str(e)
    if len(final_result_dict) == 0:
        final_results = [[]]
    else:
        final_results = getMostFrequentResult(final_result_dict)

    predicted_sql_direct = [{"sql":direct_json["predicted_sql"],"type":"direct"}]


    predicted_sql_filter = [{"sql":filter_json["predicted_sql"],"type":"filter"}]

    predicted_sql_merge = [{"sql":merge_json["predicted_sql"],"type":"merge"}]
    sqls = predicted_sql_direct + predicted_sql_filter + predicted_sql_merge
    sqls = get_best_sqls(sqls,db_path,final_results)
    if len(sqls) == 0:
        sqls = [random.choice(predicted_sql_direct + predicted_sql_filter + predicted_sql_merge)]
        predicted_sql = sqls[0]["sql"]
    elif len(sqls) == 1:
        predicted_sql = sqls[0]["sql"]
    else:
        prompt = [
        {
            "role": "system",
            "content": "You are an expert Python developer specializing in data analysis and database management. Your role is to assist users in selecting the most optimal SQL query from a set of SQL queries based on the answers provided by the queries. The selected SQL should be the one that most directly and accurately answers the user's question, with a focus on the query's structure and relevance to the user's needs. Your solutions should be precise, efficient, and easy to understand."
        },
        {
            "role": "user",
            "content":
                """
        # Question: {question}
        #extral knowledge:{evidence}
        # Database structure: {db_schema}
        # {sql_results}    
        # return ```sql``` and the code should be valid sql code
        """
        }
    ]
        sql_results = ""
        for i,pre_sql in enumerate(sqls):
            sql_results += f"sql{i}: {pre_sql['sql']} result:{util.formatOutput(pre_sql['result'])} \n"
        prompt[1]["content"] = prompt[1]["content"].format(
            db_schema=csv_schema,
            question=question,
            evidence=evidence,
            sql_results=sql_results
        )
        response,token_cost_ = chat_with_llm(prompt,n=1,temperature=0,max_tokens=8192)
        predicted_sql = util.getSql(response[0])

    try:
        result_predicted_sql = util.execute_sql(db_path, predicted_sql)
    except BaseException as e:
        result_predicted_sql = str(e)
    is_equal_sql = eval_exec_match(db_path, predicted_sql, sql, False, False, False) or eval_exec_match(db_path, predicted_sql, sql, False, True, False)
    ves_score = get_time_ratio(predicted_sql, sql, db_path, is_equal_sql, 10)

    is_equal = (
            resultSqlListEqCode_codeNullFalse(code_direct_result,result_sql_answer)
            or resultSqlListEqCode_codeNullFalse(code_filter_result,result_sql_answer)
            or resultSqlListEqCode_codeNullFalse(code_merge_result,result_sql_answer)
    )or(
            resultSqlListEqCode_codeNullFalse(code_direct_result,result_sql_answer_removeDistinct)
            or resultSqlListEqCode_codeNullFalse(code_filter_result,result_sql_answer_removeDistinct)
            or resultSqlListEqCode_codeNullFalse(code_merge_result,result_sql_answer_removeDistinct)
    )

    # Get question hardness
    hardness = util.getHardness(question)

    type = sqls[0]["type"]
    for i in range(len(sqls)):
        if predicted_sql == sqls[i]["sql"]:
            type = sqls[i]["type"]
    output_data = {
        "type": type,
        "question": question,
        "ori_sql": sql,
        "sql_result": result_sql_answer,
        "is_code_equal": is_equal,
        "predicted_code": str(final_results),
        "csv_schema": csv_schema,
        "predicted_sql": predicted_sql,
        "predicted_sql_result": str(result_predicted_sql),
        "is_sql_equal": is_equal_sql,
        "hardness": hardness,
        "ves_score": ves_score

    }

    util.printDict(output_log_file, output_data)

    with open(output_file, "w") as out_f:
        json.dump(output_data, out_f, indent=4)

    return {
        "type":sqls[0]["type"],
        "ves_score": ves_score,
        "file_id": os.path.basename(file_paths[0]).split("_")[0],
        "is_code_equal": is_equal,
        "is_sql_equal": is_equal_sql,
        "hardness": hardness
    }

def main():
    data_dirs = ["final_direct","final_filter","final_merge"]
    output_dir = "final_sql"
    db_base_dir = "database"

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "log"), exist_ok=True)
    files = [(os.path.join(data_dirs[0], f),os.path.join(data_dirs[1], f),os.path.join(data_dirs[2], f)) for f in os.listdir(data_dirs[0]) if f[0].isdigit() and f.endswith(".json")]

    files = files[:]

    results = []
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(process_file, file_path, output_dir, db_base_dir)
            for file_path in files
        ]
        for future in futures:
            results.append(future.result())
    # Initialize the statistics dictionaries
    stats = defaultdict(list)
    hardness_summary = defaultdict(lambda: {"total": 0, "code_correct": 0, "sql_correct": 0, "ves_scores": []})
    stats["type_distribution"] = {}
    stats["type_hardness_distribution"] = defaultdict(lambda: defaultdict(int))  # Now initialized for hardness -> type

    for result in results:
        hardness = result["hardness"]
        is_equal = result["is_code_equal"]
        is_equal_sql = result["is_sql_equal"]
        ves_score = result["ves_score"]
        file_id = result["file_id"]
        result_type = result["type"]

        # Initialize type-specific statistics
        if result_type not in stats["type_distribution"]:
            stats["type_distribution"][result_type] = 0

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

        # Update type-specific statistics (counts of each type and its associated hardness levels)
        stats["type_distribution"][result_type] += 1
        stats["type_hardness_distribution"][hardness][result_type] += 1  # Now using hardness -> type

    # Calculate code and SQL accuracy for each hardness level
    hardness_accuracy = {
        hardness: {
            "ves_score": compute_ves(summary["ves_scores"]),
            "code_accuracy": summary["code_correct"] / summary["total"] if summary["total"] > 0 else 0,
            "sql_accuracy": summary["sql_correct"] / summary["total"] if summary["total"] > 0 else 0,
            "total": summary["total"]
        }
        for hardness, summary in hardness_summary.items()
    }

    # Calculate type distribution proportions
    stats_summary = {
        "code_accuracy": sum(stats["code_correct"]) / sum(stats["total"]) if sum(stats["total"]) > 0 else 0,
        "sql_accuracy": sum(stats["sql_correct"]) / sum(stats["total"]) if sum(stats["total"]) > 0 else 0,
        "code_correct_sql_wrong_count": len(stats["code_correct_sql_wrong"]),
        "sql_correct_code_wrong_count": len(stats["sql_correct_code_wrong"]),
        "both_wrong_count": len(stats["both_wrong"]),
        "code_correct_sql_wrong_ids": stats["code_correct_sql_wrong"],
        "sql_correct_code_wrong_ids": stats["sql_correct_code_wrong"],
        "both_wrong_ids": stats["both_wrong"],
        "hardness_accuracy": hardness_accuracy,
        "total_ves_score": compute_ves([result["ves_score"] for result in results]),
        "type_distribution": {
            "counts": stats["type_distribution"],
            "proportions": {t: count / sum(stats["total"]) for t, count in stats["type_distribution"].items()}
        },
        "type_hardness_distribution": {
            h: {
                t: {
                    "count": count,
                    "proportion": count / sum(stats["type_hardness_distribution"][h].values()) if sum(
                        stats["type_hardness_distribution"][h].values()) > 0 else 0
                }
                for t, count in stats["type_hardness_distribution"][h].items()
            }
            for h in stats["type_hardness_distribution"]
        }
    }

    print(stats_summary)
    # Write statistics
    stats_file = os.path.join(output_dir, "statistic.json")
    with open(stats_file, "w") as stats_f:
        json.dump(stats_summary, stats_f, indent=4)


if __name__ == "__main__":
    main()
