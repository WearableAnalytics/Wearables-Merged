package main

var (
	serviceURL       string
	jwtToken         string
	messageSize      int
	rampUpDuration   int // in seconds
	duration         int // in seconds
	rampDownDuration int // in seconds
	rps              int
)

func loadConfig() {
	serviceURL = mustGetEnvString("SERVICE_URL")
	jwtToken = mustGetEnvString("JWT_TOKEN")
	messageSize = mustGetEnvInt("MESSAGE_SIZE")
	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	duration = mustGetEnvInt("DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	rps = mustGetEnvInt("RPS")
}

func main() {
	// TODO: loadConfig()

}
