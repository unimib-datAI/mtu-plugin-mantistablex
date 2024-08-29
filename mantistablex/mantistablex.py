import os
import sys
import json
import requests


error_template = """
        <div style="display:flex;flex-direction:column;gap:0.5rem;">
            <h2 style="font-weight:bold;">Lexicalized Table</h2>
            <div style="padding:0.5rem;border: 1px solid red;">
                <p style="color:red;">
                    Please provide all the necessary inputs and variables in .env to execute the mantistablex plugin
                </p>
            </div>
        </div>
        """


# Configuration
try:
    GPT_KEY = os.environ["GPT_KEY"]
    GPT_ENDPOINT = os.environ["GPT_ENDPOINT"]
except Exception as e:
    print("ENTRA IN ERRORE")
    with open(f"{os.path.dirname(os.path.realpath(__file__))}/output.html", 'w', encoding="utf-8") as file:
        file.write(error_template)
    sys.exit(0)

prompt_template = (
    "Below is an instruction that describes a task, paired with an input that provides further context. "
    "Write a response that appropriately completes the request.\n\n"
    "### Instruction:\n{instruction}\n\n### Input:\n{input}\n\n### Response:\n"
)

headers = {
    "Content-Type": "application/json",
    "api-key": GPT_KEY,
}


def get_table_portion(table, background: int, interest: int):
    """Get Table Portion for Lexicalization"""
    # Get rows and columns available
    number_of_cols = len(table["header"])
    cols = number_of_cols
    rows = len(table["rows"])
    if interest == 0:
        rows = 8
    if background == 0:
        if interest == 1:
            cols = 3
        else:
            cols = 2
    else:
        if number_of_cols > 6:
            cols = number_of_cols
            # cols = [0, number_of_cols - 3,
            #        number_of_cols - 2, number_of_cols - 1]

    # Dataset Name
    dataset_name = table["datasetName"]
    # Table Name
    table_name = table["tableName"]
    # New Header
    new_header = table["header"][0:cols]
    # Status
    status = table["status"]
    # ROWS
    new_rows = []
    for row in table["rows"][0:rows]:
        new_rows.append({
            "idRow": row["idRow"],
            "data": row["data"][0:cols]
        })
    # CEA
    new_semantic_annotations_cea = []
    for annotation in table["semanticAnnotations"]["cea"]:
        if int(annotation["idColumn"]) < cols and int(annotation["idRow"]) < rows:
            new_semantic_annotations_cea.append(annotation)
    # CTA
    new_semantic_annotations_cta = []
    for annotation in table["semanticAnnotations"]["cta"]:
        if int(annotation["idColumn"]) < cols:
            new_semantic_annotations_cta.append(annotation)

    # CTA
    new_semantic_annotations_cpa = []
    for annotation in table["semanticAnnotations"]["cpa"]:
        if int(annotation["idSourceColumn"]) < cols and int(annotation["idTargetColumn"]) < cols:
            new_semantic_annotations_cpa.append(annotation)

    return {
        "datasetName": dataset_name,
        "tableName": table_name,
        "header": new_header,
        "rows": new_rows,
        "semanticAnnotations": {
            "cea": new_semantic_annotations_cea,
            "cta": new_semantic_annotations_cta,
            "cpa": new_semantic_annotations_cpa
        },
        "metadata": {"column": table["metadata"]["column"][0:cols]},
        "status": status
    }


table_input_path = f"{os.path.dirname(os.path.realpath(__file__))}/input.json"
file_input = open(table_input_path, encoding="utf-8")
original_table = json.load(file_input)

input_data_path = f"{os.path.dirname(os.path.realpath(__file__))}/inputData.json"
file_input_data = open(input_data_path, encoding="utf-8")
input_data: dict = json.load(file_input_data)

background = input_data.get("background", 0)
interest = input_data.get("interest", 0)

new_table = get_table_portion(
    original_table["data"], background=background, interest=interest)

# CEA
cea_dict = {}
for annotation in new_table["semanticAnnotations"]["cea"]:
    column = annotation["idColumn"]
    row = annotation["idRow"]
    entities = annotation["entities"]
    if len(entities) > 0:
        entity = entities[0]
        cea_dict[f"{row}_{column}"] = {
            "id": entity["id"],
            "name": entity["name"]
        }
    else:
        continue

# CTA
cta_dict = {}
for annotation in new_table["semanticAnnotations"]["cta"]:
    column = annotation["idColumn"]
    types = annotation["types"]
    if len(types) > 0:
        winning_type = types[0]
        cta_dict[column] = {
            "id": winning_type["id"],
            "name": winning_type["name"]
        }
    else:
        continue

# CPA
cpa_dict = {}
for annotation in new_table["semanticAnnotations"]["cpa"]:
    source_column = annotation["idSourceColumn"]
    target_column = annotation["idTargetColumn"]
    predicates = annotation["predicates"]
    if len(predicates) > 0:
        winning_predicate = predicates[0]
        cpa_dict[f"{source_column}_{target_column}"] = {
            "id": winning_predicate["id"],
            "name": winning_predicate["name"]
        }
    else:
        continue

table_representation: str = ""

for row in new_table["rows"]:
    idRow = row["idRow"]
    for first_index, first_cell in enumerate(row["data"]):
        col_type_first = cta_dict[first_index]["name"] if first_index in cta_dict else ""
        subject = cea_dict[f"{idRow}_{first_index}"]["name"] if f"{idRow}_{first_index}" in cea_dict else first_cell
        for second_index, second_cell in enumerate(row["data"]):
            if second_index > first_index:
                col_type_second = cta_dict[second_index]["name"] if second_index in cta_dict else ""
                predicate = cpa_dict[f"{first_index}_{second_index}"][
                    "name"] if f"{first_index}_{second_index}" in cpa_dict else "[UNKNOWN]"
                obj = cea_dict[f"{idRow}_{second_index}"]["name"] if f"{idRow}_{second_index}" in cea_dict else second_cell

                table_representation += f"<{col_type_first} {subject}, {predicate}, {col_type_second} {obj}>;"

template_prompt = {
    "instruction": "This is a lexicalization task. The goal for this task is to lexicalize the given table. You will be given an annotated table in rdf triples, with annotations from Wikidata. The annotations are between '<' and '>'.",
    "input": table_representation
}
prompt = prompt_template.format(**template_prompt)

# Payload for the request
payload = {
    "messages": [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
        }
    ],
    "temperature": 0.8,
    "top_p": 0.9,
    "max_tokens": 512,
}


# Send request
try:
    response = requests.post(
        GPT_ENDPOINT, headers=headers, json=payload, timeout=10000)
    # Will raise an HTTPError if the HTTP request returned an unsuccessful status code
    response.raise_for_status()
except requests.RequestException as e:
    with open(f"{os.path.dirname(os.path.realpath(__file__))}/output.html", 'w', encoding="utf-8") as file:
        file.write(error_template)
    sys.exit(0)

# Handle the response as needed (e.g., print or process)
choices = response.json().get("choices", None)
first_response: dict = choices[0] if choices is not None else None
message: dict = first_response.get(
    "message", None) if first_response is not None else None
content = message.get(
    "content", None) if first_response is not None else "Error on generating response"

output_template = f"""
<div style="display:flex;flex-direction:column;gap:0.5rem;">
    <h2 style="font-weight:bold;">Lexicalized Table</h2>
    <div style="padding:0.5rem;border: 1px solid #4CAF50;">
        <p>
            {content}
        </p>
    </div>
</div>
"""

with open(f"{os.path.dirname(os.path.realpath(__file__))}/output.html", 'w', encoding="utf-8") as file:
    file.write(output_template)
