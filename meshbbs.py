import meshtastic
import time
import json
import meshtastic.tcp_interface
from meshtastic.mesh_interface import MeshInterface
from pubsub import pub

config = {}

connection_lost = False

help_text = f"""
{config.get("bbs_name", 'Mesh BBS')}
Commands:
- (h)elp: Show this help message
- (b)ulletins: Show active bulletins
- (p)ost <message>: Post a new bulletin (max length {config.get("max_message_length", 200)} characters)
- db <number>: Delete bulletin (own bulletins only)
- stats: Show some info about this BBS
- users: List known users
- nodes: List known nodes
- page: Page sysop (if you want to chat)
- ping: Respond with 'pong'
"""

def load():
    global config
    try:
        with open('bbs.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

def save():
    global config
    with open('bbs.json', 'w') as f:
        json.dump(config, f, indent=4)

def get_stats(interface):
    return f"Stats: I know of {len(interface.nodes.keys())} nodes. System has {len(config.get('users', []))} users."

def get_nodes(interface):
    out = "Nodes I can see:"
    for node_id, node in interface.nodes.items():
        print(node["user"]["shortName"])
        print(node["user"]["longName"])
        out += f"\n - {node["user"]["shortName"]} ({node["user"]["longName"]} {node.get("hopsAway", "-")} hops away)"

        user = config.get("users", {}).get(node_id, {})
        if user and len(user.get("shortName", "")) == 0:
            user["shortName"] = node["user"]["shortName"] if node["user"] else ""
            user["longName"] = node["user"]["longName"] if node["user"] else ""
            save()

    return out

def get_users(interface):
    out = "BBS users:"
    for user_id, user in config.get("users", {}).items():
        ts = time.strftime('%d.%m - %H:%M', time.localtime(user['last_seen']))
        out += f"\n - {get_user_display_name(interface, user_id)} seen {ts}"
    return out

def get_user_display_name(interface, user_id):
    user = config.get("users", {}).get(user_id, {})
    sn = user.get("shortName", "Unknown")
    ln = user.get("longName", "Unknown")
    if sn != "Unknown" or ln != "Unknown":
        return f"{sn} ({ln})"
    return user_id

def send_bulletin(interface, user, bulletin):
    ts = time.strftime('%d.%m - %H:%M', time.localtime(bulletin['timestamp']))
    send_message(interface, f"Bulletin #{bulletin['number']} by {get_user_display_name(interface, bulletin['author'])} at {ts}:\n{bulletin['text']}", destination_id=user)

def check_new_bulletins(interface, user):
    user_info = config.get("users", {}).get(user, {})
    last_read = user_info.get("last_read_bulletin", 0)
    new_bulletins = [b for b in config.get("bulletins", []) if b["number"] > last_read]
    if new_bulletins:
        for bulletin in new_bulletins:
            if bulletin['author'] == user:
                continue
            send_message(interface, f"New bulletin by: {bulletin['author']}", destination_id=user)
            send_bulletin(interface, user, bulletin)
        
        if bulletin['number'] > user_info["last_read_bulletin"]:
            user_info["last_read_bulletin"] = bulletin['number']
            save()

def handle_command(interface, user, message):
    print(f"Received from {user}: {message} {interface}")
    if message.lower() == "ping":
        send_message(interface, "pong", destination_id=user)
    elif message.lower() == "page":
        send_message(interface, f"{get_user_display_name(interface, user)} wants to chat", destination_id=config['admin_id'])
    elif message.lower() == "stats":
        send_message(interface, get_stats(interface), destination_id=user)
    elif message.lower() == "users":
        send_message(interface, get_users(interface), destination_id=user)
    elif message.lower() == "nodes":
        send_message(interface, get_nodes(interface), destination_id=user)
    elif message.lower() == "help" or message.lower() == "h":
        send_message(interface, help_text, destination_id=user)
    elif message.lower().startswith("db "):
        parts = message.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            send_message(interface, "Error: Invalid bulletin number. Usage: db <number>", destination_id=user)
        else:
            bulletin_number = int(parts[1].strip())
            bulletins = config.get("bulletins", [])
            bulletin_to_delete = next((b for b in bulletins if b["number"] == bulletin_number), None)
            if not bulletin_to_delete:
                send_message(interface, f"Error: Bulletin #{bulletin_number} not found.", destination_id=user)
            elif not (bulletin_to_delete['author'] == user or user == config.get('admin_id')):
                send_message(interface, "Error: You can only delete your own bulletins.", destination_id=user)
            else:
                config['bulletins'] = [b for b in bulletins if b["number"] != bulletin_number]
                save()
                send_message(interface, f"Bulletin #{bulletin_number} deleted.", destination_id=user)
    elif message.lower() == "bulletins" or message.lower() == "b":
        bulletins = config.get("bulletins", [])
        if bulletins:
            for b in bulletins:
                print(b)
                send_bulletin(interface, user, b)
        else:
            send_message(interface, "No bulletins available.", destination_id=user)
    elif message.lower().startswith("post ") or message.lower().startswith("p "):
        parts = message.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            send_message(interface, "Error: No message provided. Usage: post <message>", destination_id=user)
        else:
            bulletin_text = parts[1].strip()
            if len(bulletin_text) > config.get("max_message_length", 200):
                send_message(interface, f"Error: Message too long. Max length is {config.get('max_message_length', 200)} characters.", destination_id=user)
            else:
                bulletins = config.setdefault("bulletins", [])
                config['bulletin_counter'] = config.get('bulletin_counter') + 1
                bulletins.append({
                    "number": config['bulletin_counter'],
                    "text": bulletin_text,
                    "author": user,
                    "timestamp": time.time()
                })
                save()
                send_message(interface, f"Bulletin posted as #{config['bulletin_counter']}.", destination_id=user)
    else:
        send_message(interface, "?SYNTAX ERROR, type 'help' to list commands.", destination_id=user)
    

def on_receive(packet, interface):
    decoded = packet.get('decoded', {})
    if decoded.get('portnum', '') != 'TEXT_MESSAGE_APP':
        return
    toid = packet.get('toId', 'unknown')

    if(toid == '^all'):
        return

    user = packet.get('fromId', 'unknown')

    if user not in config.get("users", {}):
        config.setdefault("users", {})[user] = {
            "first_seen": time.time(),
            "last_seen": time.time(),
            "messages_sent": 0,
            "last_read_bulletin": 0
        }
        send_message(interface, config.get("welcome_message", "Welcome!"), destination_id=user)

    config["users"][user]["last_seen"] = time.time()
    save()

    try:
        handle_command(interface, user, decoded.get('text', ''))
        check_new_bulletins(interface, user)
    except MeshInterface.MeshInterfaceError as e:
        print(f"MeshInterface error: {e}")

def on_disconnect(interface):
    global connection_lost
    print(f"Disconnected from Meshtastic device!")
    connection_lost = True

def send_message(interface, text, destination_id=None):
    try:
        interface.sendText(text, destinationId=destination_id)
    except MeshInterface.MeshInterfaceError as e:
        print(f"Error sending message: {e}. Splitting message.")
        while len(text) > 200:
            part = text[:200]
            interface.sendText(part, destinationId=destination_id)
            text = text[200:]
        interface.sendText(text, destinationId=destination_id)

def main():
    # Connect to the Meshtastic device via TCP
    global connection_lost
    try:
        while True:
            connection_lost = False
            interface = meshtastic.tcp_interface.TCPInterface(hostname=config.get("node_ip", "127.0.0.1")
            pub.subscribe(on_receive, "meshtastic.receive")
            pub.subscribe(on_disconnect, "meshtastic.connection.lost")

            print("Connected to Meshtastic device. Listening for messages...")
            get_users(interface)
            ourNode = interface.getNode(meshtastic.LOCAL_ADDR)
            while not connection_lost:
                time.sleep(0.1)
            print("Connection lost. Reconnecting in 5 seconds...")
            time.sleep(5)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    load()
    main()
