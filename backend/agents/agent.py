from agents.memory import remember, recall
from agents.tools import web_search
from agents.planner import decide

class Agent:
    def run(self, message):
        action = decide(message)
        
        # 1. మెమరీ సేవింగ్ లాజిక్ (My name is... అన్నప్పుడు గుర్తుపెట్టుకోవడానికి)
        if action == "memory":
            if "my name is" in message.lower():
                name = message.split("my name is", 1)[1].strip()
                remember("name", name)
                return f"✅ Okay! I'll remember that your name is {name}."
        
        # 2. పేరు అడిగినప్పుడు గుర్తుచేసే లాజిక్ (Recall logic)
        msg = message.lower().strip()
        if msg in [
            "who am i?",
            "who am i",
            "what is my name?",
            "what is my name"
        ]:
            name = recall("name")
            if name:
                return f"Your name is {name}."
            else:
                return "I don't know your name yet. Tell me by saying 'My name is ...'."
        
        # 3. వెబ్ సెర్చ్ లాజిక్ (Web search block సరిగ్గా ఇండెంట్ చేయబడింది)
        if action == "web":
            results = web_search(message)
            text = ""
            for item in results:
                text += f"Title: {item['title']}\nContent: {item['body']}\nSource: {item['link']}\n\n"
            
            return {
                "tool": "web",
                "context": text
            }
            
        return None