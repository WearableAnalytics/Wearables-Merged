package message

type Message struct {
	DeviceInfo      DeviceInfo   `json:"deviceInfo,omitempty"`
	BatchInfo       BatchInfo    `json:"batchInfo,omitempty"`
	Measurements    Measurements `json:"measurements,omitempty"`
	SourceName      string       `json:"sourceName,omitempty"`
	TotalStepsToday *int         `json:"totalStepsToday,omitempty"`
	Timestamp       string       `json:"timestamp,omitempty"`
}

type DeviceInfo struct {
	Platform           string `json:"platform,omitempty"`
	DeviceID           string `json:"deviceID,omitempty"`
	AuthorizationToken string `json:"authorizationToken,omitempty"`
}

type BatchInfo struct {
	// Timestamps
	CollectionStart string `json:"collectionStart,omitempty"`
	CollectionEnd   string `json:"collectionEnd,omitempty"`
}

type Measurements struct {
	Instantaneous []Instantaneous `json:"instantaneous"`
	Cumulative    []Cumulative    `json:"cumulative"`
	Duration      []Duration      `json:"duration"`
}

type Instantaneous struct {
	Type      string `json:"type,omitempty"`
	Value     int    `json:"value,omitempty"`
	Unit      string `json:"unit,omitempty"`
	Timestamp string `json:"timestamp,omitempty"`
}

type Cumulative struct {
	Type  string `json:"type,omitempty"`
	Value int    `json:"value,omitempty"`
	Unit  string `json:"unit,omitempty"`
	// Time
	PeriodStart string `json:"periodStart,omitempty"`
	PeriodEnd   string `json:"periodEnd,omitempty"`
	Duration    int    `json:"duration,omitempty"` //sec
}

type Duration struct{}
