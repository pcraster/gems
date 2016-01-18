#!/usr/bin/env python
from flask.ext.script import Manager, Shell, Server
from webapp import *

import select
from sqlalchemy import text
import datetime
manager = Manager(app)


from sqlalchemy.event import listen
from sqlalchemy.pool import Pool


manager.add_command("runserver", Server())
manager.add_command("shell", Shell())

@manager.command
def createdb():
    """
    Create the database.
    """
    db.create_all()

@manager.command
def dropdb():
    """
    Drop the database. Use with care!
    """
    db.drop_all()


@manager.command
@manager.option('-u', '--username', help='Username you want to reset password for')
def reset_password(username):
    """
    Hard reset of user password
    """
    user = User.query.filter(User.username==username).one()
    new_password = ''.join(random.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    user.password = user_manager.hash_password(new_password)
    db.session.commit()
    print "New password for user '%s': %s"%(username,new_password)

@manager.command
def notifications():
    conn = db.engine.connect()
    conn.execute(text("LISTEN gemsnotifications;").execution_options(autocommit=True))
    while 1:
        if select.select([conn.connection],[],[],5) == ([],[],[]):
            print "Timeout"
        else:
            conn.connection.poll()
            while conn.connection.notifies:
                notify = conn.connection.notifies.pop()
                print "Got NOTIFY:", datetime.datetime.now(), notify.pid, notify.channel, notify.payload

@manager.command
def notify():
    listen(Pool, "gemsnotification", my_on_connect)
    
def my_on_connect(**kwargs):
    print "NOTIFICASTION!!"
    

if __name__=="__main__":
    manager.run()