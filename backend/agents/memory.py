from database import remember_memory, recall_memory

def remember(key, value, user_id):
    return remember_memory(key, value, user_id)

def recall(key, user_id):
    return recall_memory(key, user_id)
