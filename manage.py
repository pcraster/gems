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

if __name__=="__main__":
    manager.run()