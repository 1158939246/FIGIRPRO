from typing import List

import openai

openai.base_url = ''
openai.api_key = ""

def chat_with_llm(messages,**args)->(List[str],dict[str,int]):
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        # stop=["<end_of_turn>"],
        **args
    )
    context={
        "prompt_tokens":response.usage.prompt_tokens,
        "completion_tokens":response.usage.completion_tokens
    }
    return [item.message.content for item in response.choices],context
if __name__ == '__main__':
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "How do I write a loop in Python?"},
        {"role": "assistant", "content": "You can write a loop in Python using the 'for' or 'while' keywords. Here's an example of a 'for' loop that prints the numbers from 1 to 5:"},
        {"role": "user", "content": "Thank you!"},
    ]
    response = chat_with_llm(messages,n=2,temperature=0.5,max_tokens=4096)
    print(response)