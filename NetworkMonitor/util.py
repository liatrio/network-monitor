import subprocess

def ping(host):
	"""Pings `host`, returns average rtt and jitter"""
	cmd = 'ping {} -c 5 -i 0.2 -q'.format(host) # host could be nasty!!! careful
	try:
		status = subprocess.run(cmd.split(), stdout=subprocess.PIPE, timeout=5)
	except subprocess.TimeoutExpired:
		raise ValueError('Host timed out')
	if status.returncode != 0:
		raise ValueError('Host not reachable')
	output = status.stdout.decode('utf-8')
	stat_index = output.find('=')+2
	min_rtt, avg_rtt, max_rtt, mdev_rt = output[stat_index:].split('/')
	return float(avg_rtt), float(max_rtt) - float(min_rtt)

