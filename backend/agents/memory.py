from database import remember_memory, recall_memory

def remember(key, value):
    remember_memory(key, value)

def recall(key):
    return recall_memory(key)