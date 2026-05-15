import os
import re
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from tools import web_search, scrape_url

load_dotenv()

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0
)


class Msg:
    def __init__(self, content):
        self.content = content


# ── Search Agent ──────────────────────────────────────────────────────────────
def build_search_agent(max_results: int = 5):
    class SearchAgent:
        def __init__(self, n):
            self.n = n
        def invoke(self, data):
            query = data["messages"][0][1]
            result = web_search.invoke({"query": query, "max_results": self.n})
            return {"messages": [Msg(result)]}
    return SearchAgent(max_results)


# ── Reader Agent (FIXED: extracts first valid URL before scraping) ─────────────
def build_reader_agent():
    class ReaderAgent:
        def invoke(self, data):
            raw_input = data["messages"][0][1]
            url_match = re.search(r'https?://[^\s\)\"\']+', raw_input)
            if url_match:
                url = url_match.group(0).rstrip(".,;)")
            else:
                return {"messages": [Msg("No valid URL found in search results to scrape.")]}
            result = scrape_url.invoke(url)
            return {"messages": [Msg(f"[Source: {url}]\n\n{result}")]}
    return ReaderAgent()


# ── Writer Chain factory ───────────────────────────────────────────────────────
def build_writer_chain(report_length: str = "standard"):
    length_instructions = {
        "brief":    "Write a concise report of 300-500 words with the key findings only.",
        "standard": "Write a thorough report of 700-1000 words with sections and detail.",
        "detailed": "Write a comprehensive long-form report of 1500-2500 words with full analysis, subheadings, and examples.",
    }
    length_guide = length_instructions.get(report_length, length_instructions["standard"])

    writer_prompt = ChatPromptTemplate.from_messages([
        ("system",
         f"""You are an expert research writer. {length_guide}

Format your report in clean Markdown with:
- A compelling title (# heading)
- An executive summary section
- Clearly labelled sections with ## headings
- A Sources section at the end listing every URL used as a numbered Markdown list

Always include at least one inline citation like [Source](url) when referencing a specific fact."""),
        ("human", "Topic: {topic}\n\nResearch material:\n{research}")
    ])

    return writer_prompt | llm | StrOutputParser()


# ── Critic Chain ───────────────────────────────────────────────────────────────
critic_prompt = ChatPromptTemplate.from_messages([
    ("system",
     """You are a strict but constructive research critic.
Evaluate the report on:
1. **Accuracy** - Are facts well-supported?
2. **Depth** - Is the analysis thorough?
3. **Structure** - Is it clearly organised?
4. **Citations** - Are sources referenced?
5. **Overall score** - Give a score out of 10.

Format feedback with these exact ## headings."""),
    ("human", "Review this report:\n\n{report}")
])

critic_chain = critic_prompt | llm | StrOutputParser()
