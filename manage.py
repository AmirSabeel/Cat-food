"""Create or reset an administrator without storing a password in code."""
import getpass
from server import init_db,create_admin
if __name__=='__main__':
    init_db()
    username=input('Admin username: ').strip()
    password=getpass.getpass('Password (12+ characters): ')
    if password!=getpass.getpass('Repeat password: '):raise SystemExit('Passwords did not match.')
    try:create_admin(username,password)
    except ValueError as e:raise SystemExit(str(e))
    print('Administrator saved. Sign in at /admin.')
