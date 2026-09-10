import { NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";

/**
 * POST /api/token
 *
 * Generates a LiveKit room access token for the frontend to connect
 * to the LiveKit room where the RailVox agent is running.
 */
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { room_name, participant_name } = body;

    const apiKey = process.env.LIVEKIT_API_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET;
    const livekitUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL;

    if (!apiKey || !apiSecret || !livekitUrl) {
      return NextResponse.json(
        {
          error:
            "LiveKit credentials not configured. Set LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and NEXT_PUBLIC_LIVEKIT_URL in .env.local",
        },
        { status: 500 }
      );
    }

    const roomName = room_name || `railvox-${Date.now()}`;
    const participantName = participant_name || "user";

    // Create access token
    const token = new AccessToken(apiKey, apiSecret, {
      identity: participantName,
      name: participantName,
    });

    token.addGrant({
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
      canPublishData: true,
    });

    const jwt = await token.toJwt();

    return NextResponse.json({
      token: jwt,
      url: livekitUrl,
      room_name: roomName,
    });
  } catch (error) {
    console.error("Token generation error:", error);
    return NextResponse.json(
      { error: "Failed to generate token" },
      { status: 500 }
    );
  }
}
