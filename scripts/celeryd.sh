#! /bin/sh
./manage.py celeryd --verbosity=2 --loglevel=DEBUG -c 4
