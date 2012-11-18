Network connection life cycle
=============================

Communication with a LoBotomy server is done by opening a network socket (TCP) to it and starting a conversation.
To keep things simple, such a conversation is done by sending strings over the network connection.
A single command consists of the command's name and its arguments separated by spaces, terminated with a newline character (`\n`).
Arguments are all encoded as strings over the wire, so a float will be sent as `"0.12345"`, for example.
Note that the server is the one determining the precision of floating point values; `"0.1111111111111111111111111111111111111111111111"` will likely be truncated to `0.111111111111` or similar, without the client being notified.
The precision of floating point values is considered to be sufficient for the use case of LoBotomy (requesting actions on the edge of precision limits are at the client's risk ;)).

So, for example, a command the client might use to tell the server it wants to join the game could be constructed and set like this:

```java
// define our name to be Henk
String name = "Henk";
// write the join command, followed by a space and our name, terminated with a newline
output.write("join" + " " + name + "\n");
```

As we model client/server communication as a conversation, the server could respond with a welcome message, read by the client as such:

```java
// read a line from our input
String line = input.readLine();
// parse the line into a command and arguments
String[] parts = line.split(" ");
// handle the command
if (parts[0].equals("welcome")) {
	handleWelcome(parts);
}
```

The above might not be the most efficient code, but the idea is clear.

Protocol
--------

The conversation between client and server supports the commands listed below.
It should be noted that the use of radians and distance is always relative to the player receiving the information.
The internal location on the battlefield as tracked by the server is never exposed but is not needed either as the battlefield wraps.
The same holds for angles: a player is free to define where zero radians is, as long as the reference point remains the same.

Commands are listed in conversation-like order, the sending party is explicitly stated.

### join
Format: `join name`

Sent by you to request to join the game using a particular name (containing just alphanumeric characters).

### welcome
Format: `welcome version energy heal turn-duration turns-left`

Sent by the server to welcome you to the game and provide some game settings:

1. **version** (integer): the protocol version used by the server;
1. **energy** (float): the starting and maximum energy for players;
1. **heal** (float): the amount of energy players get at the end of each turn;
1. **turn-duration** (integer): the number of milliseconds a turn will take;
1. **turns-left** (integer): the number of turns the current game has left (or -1 if the game is run perpetual).

### spawn
Format: `spawn`

Sent by you to request to be put on the battlefield in the next turn.

### begin
Format: `begin turn-number energy`

Sent by the sever to indicate the start of a new round. Arguments inform you of:

1. **turn-number** (integer): an incremental identifier for the current turn;
1. **energy** (float): the amount of energy you currently have.

### move
Format: `move angle distance`

Sent by you to request a move action to be performed in the current turn with the following details:

1. **angle** (radian, float): the direction in which to move;
1. **distance** (float): the distance to move.

### fire
Format: `fire angle distance radius charge`

Sent by you to request a fire action to be performed in the current turn with the following details:

1. **angle** (radian, float): the direction in which to fire a bomb;
1. **distance** (float): the distance to fire the bomb;
1. **radius** (float): the radius of the bomb's explosion;
1. **charge** (float): the energy dissipation of the bomb (amount of damage).

### scan
Format: `scan radius`

Sent by you to request a scan action to be performed in the current turn with the following details:

1. **radius** (float): the radius of the scan, centered on you.

### end
Format: `end`

Sent by the server to indicate that no further actions will be accepted before for the current turn and it will execute the current turn.

### hit
Format: `hit name angle charge`

Sent by the server to indicate that you were hit by a bomb, with the following details:

1. **name** (string): the name of the player that fired the bomb;
1. **angle** (radian, float): the direction the blast came from (the epicenter of the blast);
1. **charge** (float): the strength of the bomb.

### death
Format: `death turns`

Sent by the server to inform you that you are dead and how long you need to wait before you can respawn (yes, that's something you need to do yourself):

1. **turns** (integer): how long you will stay dead.

### detect
Format: `detect name angle distance energy`

Sent by the server to inform you that your scan detected another player, with the following details:

1. **name** (string): the name of the detected player;
1. **angle** (radian, float): the direction of the detected player;
1. **distance** (float): the distance of the detected player;
1. **energy** (float): the amount of energy of the detected player.

### error
Format: `error error-code explanation`

Sent by the server in response to a command sent by you to indicate that the command could not be accepted, with the following details:

1. **error-code** (integer): numerical representation of the error;
1. **explanation** (string): an elaboration of the error, only serving a debug purpose (not to be used by clients in any meaningful way).

Example
-------

Below is an example of a conversation between a client and a server.
`→` indicates a message from the client to server, `←` a message from the server to the client.
Remarks are inserted after a `#`-character.

```
→ join Henk                   # join the game as Henk
← welcome 1 1.0 0.2 5000 -1
→ spawn
← begin 123 1.0               # Henk has 1.0 energy left
→ move 0.123 0.2              # take a gentle stroll…
→ scan 0.4                    # …and take a look around
← end
← detect Klaas 1.234 0.3 0.4  # Henk detected Klaas over there
← begin 124 0.6               # used 0.2 + 0.4 energy, 0.2 energy healed at end of turn
→ fire 1.123 0.2 0.3 0.4      # fire at Klaas' location with 0.3 blast radius
← end
← hit Henk 1.123 0.4          # radius was larger than distance, Henk hit himself (he's a bit 'special')
← hit Klaas 1.123 0.6         # adversary was not stupid, fired at Henk
← death 5                     # Henk died, is dead for 5 turns
```

