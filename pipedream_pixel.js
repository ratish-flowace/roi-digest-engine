import axios from "axios";

export default defineComponent({
  async run({ steps, $ }) {
    const { company = "unknown", date = "" } = steps.trigger.event.query;

    await axios.post(
      `https://www.google-analytics.com/mp/collect?measurement_id=${process.env.GA4_MEASUREMENT_ID}&api_secret=${process.env.GA4_API_SECRET}`,
      {
        client_id: company,
        events: [{ name: "email_open", params: { company_name: company, report_date: date } }],
      }
    ).catch(() => {});

    await $.respond({
      status: 200,
      headers: { "Content-Type": "image/gif", "Cache-Control": "no-cache, no-store" },
      body: Buffer.from("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7", "base64"),
    });
  },
});
