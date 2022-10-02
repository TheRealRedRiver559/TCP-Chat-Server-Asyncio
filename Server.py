import asyncio
import json
import inspect

#this is a test server, some features (most) are not working
#also a lot of things will be changed in the future such as message formats.

host, port = ('localhost', 9090)
clients = dict()
banned_users = set()
message_history =  []
chat_history = False  #experimental (may not work)
message_size = 200
username_len = 10

class Client:
    """Client class for storing client information such as task, username and more"""
    def __init__(self, reader, writer, task):
        self.reader = reader
        self.writer = writer
        self.task = task
        self.logged_in = False
        self.username = None
        self.connected = True

class Commands:
    prefix = '//'
    commands = {}
    def command(name : str, permission=1):
        def wrapper(command):
            Commands.commands[name] = [command, permission]
            return command
        return wrapper
    
    @staticmethod
    async def check_command(client, message):
        """Checks if the command usage is valid and if it is an actual command"""
        message = message.removeprefix(Commands.prefix).split() #removes the command prefix from the message
        command_name = message[0]
        paramters = message[1:len(message)] #everything above the command name is a parameter
        if command_name in Commands.commands:
            command = Commands.commands[command_name][0] #grabs the command function from the commands dict
            command_data = inspect.getfullargspec(command) #gets a argspec (argument details) for that function
            if (command_data.varargs) is not None:
                await command(client, *paramters, command=True)
            else:
                await command(client)

async def user_leave(client : Client):
    client.connected = False
    client.task.cancel()
    if client.username != None:
        del clients[client.username]
    if not client.writer.is_closing():
        client.writer.close()
        await client.writer.wait_closed()

async def send_data(client, data):
    if isinstance(data, dict):
        data = (json.dumps(data)+'\n')
    data = data.encode()
    client.writer.write(data)
    await client.writer.drain()

@Commands.command('broadcast', 5)
async def broadcast(client, *data, command=False):
    """broadcasts the message to all users, command and server side version"""
    data = ' '.join(data)
    format = {'sender':client.username, 'message':data, 'message_type':'public'}
    if command:
        format['sender'] = 'Server'

    #message_history.append(json.dumps(format)+'\n')

    for client in clients.values():
        await send_data(client, format)

@Commands.command('message', 1)
async def send_message(client, *data, command=False, message_type='private'):
    #no special format for direct messages on client side (very easy to add though)
    """Sends a 'private' message to the specified client / username"""
    format = {'sender':'Server', 'message':data, 'message_type':message_type}
    if command:
        target_username = data[0]
        if target_username in clients:
            target_client = clients[target_username]
            format['sender'] = client.username
            data = data[1:len(data)]

    data = ' '.join(data)
    format['message'] = data

    await send_data(client, format)
    if command:
        await send_data(target_client, format)

@Commands.command('users', 5)
async def users_online(client):
    #will be combined with users function eventually
    """Sends a list of all online users"""
    user_list = [x for x in clients.keys()]
    await send_message(client, f'Users online: {user_list}')

@Commands.command('banned-users', 5)
async def users_banned(client):
    #will be combined with users function eventually
    """Sends a list of all banned users"""
    user_list = [x for x in banned_users]
    await send_message(client, f'Banned users: {user_list}')

@Commands.command('ban', 1)
async def ban_user(client, *data, command=False):
    format = {'sender':'Server', 'message':'You have been banned!', 'message_type':'private'}
    if command:
        target_username = data[0]
        if target_username in clients:
            target_client = clients[target_username]
            data = data[1:len(data)]
    else:
        target_username = client.username
        target_client = client

    if len(data) >= 1:
        data = ' '.join(data)
        format['message'] = f'You have been banned for: {data}'

    await send_data(target_client, format)

    banned_users.add(target_username)
    await user_leave(target_client)

async def send_history(client):
    if len(message_history) > 0:
        history = "".join(message_history)
        await send_data(client, history)

async def receive_data(client : Client): 
    try: 
        data = (await client.reader.readuntil(b'\n')).decode()
        data = json.loads(data)
        return data
    except (Exception):
        await user_leave(client)

async def handle_client(client):
    while client.connected:
        data = await receive_data(client)
        if data == None:
            return
        try:
            message = data['message']
        except KeyError:
            await send_message(client, 'The message sent, is not in the correct format!')
            continue
        if len(message) > message_size:
            await send_message(client, 'Message exceeds the 200 char size limit.')
            continue
        elif len(message) == 0:
            continue

        if message.startswith(Commands.prefix):
            await Commands.check_command(client, message)
        else:
            await broadcast(client, message)

async def login(client : Client):
    format = {'sender':'Server', 'message':'LOGIN', 'message_type':'INFO'} #These will end up being changed to something better
    while client.logged_in == False:
        await send_data(client, format)

        login_data = await receive_data(client)
        try:
            username = login_data['username']
        except (KeyError, TypeError):
            await user_leave(client)
            return

        if len(username) > username_len:
            await send_message(client, 'Username too long!')
            continue

        if username in banned_users:
            await send_message(client, 'You are banned!')
            await user_leave(client)

        await send_message(client, 'LOGGED IN')
        client.logged_in = True
        client.username = username
        clients[client.username] = client
        await send_message(client, 'Logged in!')

async def client_connected(reader, writer):
    task = asyncio.current_task(loop=None)
    client = Client(reader, writer, task)
    await login(client)
    if chat_history:
        await send_history(client)
    await handle_client(client)

async def run_server():
    server = await asyncio.start_server(client_connected, host, port)

    print('Server started!')
    async with server:
        await server.serve_forever()

asyncio.run(run_server())
