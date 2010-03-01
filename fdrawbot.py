import sys
import socket

DefaultServer = "flockdraw.com"
DefaultPort = 443
BuffSize = 4096
DefaultEncoding = 'iso-8859-2'

class FlockDrawConnection:
    def __init__(self,
                 whiteboard,
                 username,
                 server = DefaultServer,
                 port = DefaultPort):
        self.users = []
        self.bufferIn = b""
        self.bufferOut = []
        assert "/" not in server
        self.sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        serverport = server, port
        print( "Connecting to ", serverport )
        self.sock.connect( serverport )
        print( "Connected to ", serverport )
        self.server = server
        self.port = port
        self.whiteboard = whiteboard
        self.initialize( server, whiteboard, username )
        self.hadUsers = False
        self.oweBitmap = []
    def sendLine(self, data):
        print( "Sending ", data )
        self.bufferOut.append( data.encode( DefaultEncoding ) )   
        self.bufferOut.append( b"\n" )
    def initialize(self, server, whiteboard, username):
        self.sendLine( "C whiteboard-http://{server}/{whiteboard} {username} {version}".format(
                server = server,
                whiteboard = whiteboard,
                username = username,
                version = 3
            ) )
    def deliver(self, user, data):
        self.sendLine( "D {user} {data}".format( user=user, data=data) )
    def broadcast(self, data):
        self.sendLine( "B {data}".format( data=data) )
    def deliverCommands(self, user, commands):
        self.deliver( user, self.formatCommands( commands ) )
    def broadcastCommands(self, commands):
        self.broadcast( self.formatCommands( commands ) )
    def warnWith(self, warning, data):
        limit = 60
        printLine = repr( data )
        if len( printLine ) > limit:
            printLine = repr( line[:limit] + "..." )
        print( "warning:", warning.format( data = data ), file=sys.stderr )
    def formatCommands(self, commands):
        return "\t".join( commands )
    def handleAdd(self, username):
        assert " " not in username
        self.users.append( username )
        print( "New peer:", username )
        self.hadUsers = True
    def handleRemove(self, username):
        if username in self.users:
            self.users.remove( username )
            print( "Peer leaving:", username )
        else:
            self.warnWith( "unknown peer {data} leaving", username )
    def handleMessage(self, data):
        try:
            sender, message = data.split(" ", 1)
        except ValueError:
            self.warnWith( "received message {data} without sender", username )
            return
        for command in self.parseCommands( message ):
            self.handleCommand( sender, command )
    def tryObtainBitmap(self, noAsk = []):
        import random
        try:
            user = random.choice([user for user in self.users if user not in noAsk])
        except IndexError:
            return False
        self.warnWith( "attempting to obtain bitmap from {data}", user )
        self.deliver( user, "Rq" )
        return True
    def handleRequest(self, origin, args):
        # This is the one that needs to be handled to avoid messing up
        # state for non-bots. Since we can't keep bitmap state ourselves,
        # it's a hard one. We try to obtain the bitmap from another peer.
        self.warnWith( "{data} requested bitmap", origin )
        self.oweBitmap.append( origin )
        if not self.tryObtainBitmap( noAsk = [ origin ] ):
            self.warnWith( "unable to obtain bitmap for {data}", origin )
    def handleKeypress(self, origin, args):
        print( "Event:", origin, "keypress", args )
    def handlePointerMove(self, origin, args):
        print( "Event:", origin, "move", args )
    def handlePointerSize(self, origin, args):
        print( "Event:", origin, "size", args )
    def handlePointerDown(self, origin, args):
        print( "Event:", origin, "down", args )
    def handlePointerUp(self, origin, args):
        print( "Event:", origin, "up", args )
    def handlePointerHide(self, origin, args):
        print( "Event:", origin, "hide", args )
    def handlePointerShow(self, origin, args):
        print( "Event:", origin, "show", args )
    def handleBrushChange(self, origin, args):
        print( "Event:", origin, "tool", args )
    def handleColourChange(self, origin, args):
        print( "Event:", origin, "colour", args )
    def handleFlush(self, origin, args):
        print( "Event:", origin, "flush", args )
    def debugSaveBitmap(self, filename, b64coded):
        import base64
        try:
            data = base64.b64decode( b64coded.encode( DefaultEncoding ) )
        except:
            print( "warning: data invalid", file=sys.stderr )
            return
        f = open( filename, "wb" )
        f.write( data )
        f.close()
    def handleBitmap(self, origin, data):
        for user in self.oweBitmap:
            self.warnWith( "relaying bitmap to {data}", user )
            self.deliver( user, "Bo " + data )
        self.oweBitmap = []
        import datetime
        debugName = "flockdrawdump-{user}-{whiteboard}-{timestamp}.bitmap".format(
            user = origin,
            whiteboard = self.whiteboard,
            timestamp = str( datetime.datetime.now() )
        )
        self.debugSaveBitmap( debugName, data )
    def handleCommand(self, origin, command ):
        if " " in command:
            command, args = command.split(" ", 1)
        else:
            args = None
        try:
            f = {
                'Kp': self.handleKeypress,
                'Rq': self.handleRequest,
                'Pm': self.handlePointerMove,
                'Ps': self.handlePointerSize,
                'Pd': self.handlePointerDown,
                'Pu': self.handlePointerUp,
                'Phi': self.handlePointerHide,
                'Psh': self.handlePointerShow,
                'Bch': self.handleBrushChange,
                'Cch': self.handleColourChange,
                'F': self.handleFlush,
                'Bo': self.handleBitmap,
            }[ command ]
        except KeyError:
            self.warnWith( "ignoring command {data}", command )
            if args:
                self.warnWith( "...with arguments {data}", args )
            self.warnWith( "...from {data}", origin )
        f( origin, args )
    def parseCommands(self, data):
        return data.split("\t")
    def handleLine(self, line):
        try:
            letter, rest = line.split( " ", 1 )
        except ValueError:
            self.warnWith( "ignoring line {data} (no prefix)", line )
            return
        try:
            f = {
                'A': self.handleAdd,
                'R': self.handleRemove,
                'M': self.handleMessage,
            }[letter]
        except KeyError:
            self.warnWith( "ignoring line {data} (unknown prefix)", line )
            return
        f( rest )
    def trySend(self):
        while self.bufferOut:
            data = self.bufferOut.pop(0)
            len = self.sock.send( data )
            rest = data[len:]
            if rest:
                self.bufferOut.insert( 0, rest )
                break
    def tryHandle(self):
        incoming = self.sock.recv( BuffSize )
        if incoming:
            self.bufferIn += incoming
            while True:
                elements = self.bufferIn.split( b"\n", 1 )
                if len( elements ) < 2:
                    self.bufferIn = elements[0]
                    break
                line, self.bufferIn = elements
                line = line.decode( DefaultEncoding )
                self.handleLine( line )
        return incoming
    def isAbandoned(self):
        if not self.hadUsers:
            return False
        if self.users:
            return False
        return True
    def flush(self):
        while self.bufferOut:
            self.trySend()
    def shutdown(self):
        import socket
        self.flush()
        self.sock.shutdown( socket.SHUT_WR )
        while True:
            if not self.tryHandle():
                break
        self.sock.close()

if __name__ == '__main__':
    import time
    conn = FlockDrawConnection( "testone", "observer" )
    interval = 60
    t0 = time.time() - interval
    try:
        while not conn.isAbandoned():
            conn.trySend()
            if not conn.bufferOut:
                conn.tryHandle()
            if time.time() - t0 > interval:
                print("Requesting bitmap." )
                conn.tryObtainBitmap()
                t0 = time.time()
        print( "Abandoned, leaving." )
    except KeyboardInterrupt:
        print( "Leaving after keyboard interrupt." )
    conn.shutdown()
