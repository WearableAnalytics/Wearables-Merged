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
	Platform           string `json:"platform"`
	DeviceID           string `json:"deviceId"`
	AuthorizationToken string `json:"authorizationToken"`
}

type BatchInfo struct {
	// Timestamps
	CollectionStart string `json:"collectionStart"`
	CollectionEnd   string `json:"collectionEnd"`
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
	Type  string `json:"type"`
	Value int    `json:"value"`
	Unit  string `json:"unit"`
	// Time
	PeriodStart string `json:"periodStart"`
	PeriodEnd   string `json:"periodEnd"`
	Duration    int    `json:"duration"` //sec
}

type Duration struct{}
